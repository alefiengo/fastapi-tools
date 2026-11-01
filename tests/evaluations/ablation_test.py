"""Offline regressions: synthetic observations never establish model benefit."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'evals/tools'))
import ablation
import frozen_judge as judge


class AblationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo, self.app = self.base / 'repo', self.base / 'app'
        self.repo.mkdir()
        self.app.mkdir()
        self.write(self.app / 'pyproject.toml', '[project]\nname="fixture"\n')
        self.write(self.app / 'main.py', 'raise RuntimeError("must never import application")\n')
        self.write(self.app / 'test_app.py', 'def test_placeholder(): pass\n')
        self.write(self.repo / 'skills/fastapi-testing/SKILL.md', 'skill')
        self.write(self.repo / 'skills/fastapi-database/SKILL.md', 'database')
        self.write(self.repo / 'agents/fastapi-test-writer.md', 'agent')
        self.write(self.repo / 'runtime/project_runtime.py', 'raise RuntimeError("never execute")')
        self.write(self.repo / '.mcp.json', '{}')
        self.case = self.repo / 'evals/rollback'
        self.write(self.case / 'prompt.md', '---\nmax_turns: 3\n---\nExplain how to verify rollback.\n')
        self.write(self.case / 'graders/quality.md', '---\ntype: llm\n---\nRequire independent observation after a real failure.\n')
        self.write(self.case / 'graders/activation.md', '---\ntype: tool_used\ntool: Skill\n---\n')
        self.report = json.loads((ROOT / 'tests/evaluations/fixtures/two-arm-report.json').read_text())

    @staticmethod
    def write(path, text):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def plan(self, **kwargs):
        options = dict(model='synthetic-generator-1', effort='high', host_version='synthetic-host-1',
                       canonical_judge='synthetic-judge-1', generation_timeout=30, max_turns=3)
        options.update(kwargs)
        return ablation.plan(self.repo, self.app, ['rollback'],
                             ['fastapi-testing', 'fastapi-test-writer'], **options)

    def observation(self, plan, variant='full', passed=True, *, resolved='synthetic-generator-1'):
        provenance = ablation.preparation(plan, variant, 'rollback', 0)
        arm = 'without' if variant == 'baseline' else 'with'
        report = copy.deepcopy(self.report)
        result = report['cases'][0]['arms'][arm][0]
        if resolved is None:
            result.pop('model', None)
        else:
            result['model'] = resolved
        bundle = judge.freeze(report, 'rollback', self.case, arm=arm,
                              variant=variant, provenance=provenance)
        verdict = {'id': 'quality', 'passed': passed, 'reason': 'Synthetic regression verdict',
                   'evidence': bundle['response'] if passed else ''}
        record = {'modelRequested': 'synthetic-judge-1', 'inputSha256': bundle['inputSha256'],
                  'passed': passed, 'exitCode': 0, 'judgments': [verdict],
                  'raw': {'model': 'synthetic-judge-1'}}
        judged = judge.seal({'case': 'rollback', 'canonicalModel': 'synthetic-judge-1',
                            'passed': passed, 'results': [record]})
        return bundle, judged

    def test_all_variants_preserve_inputs_and_remove_only_selected_components(self):
        for root in (self.repo, self.app):
            for relative in ('nested/AGENTS.md', 'nested/CLAUDE.md', 'nested/evals/rubric.md',
                             'docs/answers.md', '.env', '.fastapi-tools/state.json', 'node_modules/pkg/x.js'):
                self.write(root / relative, 'secret or evaluator context')
        self.write(self.repo / 'README.md', 'operator docs')
        (self.app / 'main.py').chmod(0o755)
        plan = self.plan()
        before_app = ablation.inventory(self.app)
        before_plugin = ablation.inventory(self.repo, product=True)
        with patch.object(judge.subprocess, 'run', side_effect=AssertionError('Offline must not execute')):
            for variant in ablation.VARIANTS:
                target = self.base / variant
                ablation.prepare(plan, variant, 'rollback', 0, target, self.base / (variant + '.json'))
                self.assertEqual(ablation.inventory(target / 'workspace'), before_app)
                self.assertEqual(set(p.name for p in target.iterdir()),
                                 {'workspace'} if variant == 'baseline' else {'workspace', 'plugin'})
                if variant != 'baseline':
                    self.assertEqual(ablation.inventory(target / 'plugin', product=True),
                                     ablation.variant_files(plan, variant))
        self.assertFalse((self.base / 'selected-minus/plugin/skills/fastapi-testing').exists())
        self.assertTrue((self.base / 'selected-minus/plugin/skills/fastapi-database/SKILL.md').exists())
        self.assertFalse((self.base / 'selected-minus/plugin/agents/fastapi-test-writer.md').exists())
        self.assertEqual(ablation.inventory(self.app), before_app)
        self.assertEqual(ablation.inventory(self.repo, product=True), before_plugin)

    def test_paired_criteria_missing_metrics_and_activation_remain_distinct(self):
        plan = self.plan()
        full, baseline = self.observation(plan), self.observation(plan, 'baseline', False)
        comparison = ablation.compare(plan, [full, baseline])
        self.assertIsNone(comparison['effectivenessClaim'])
        self.assertEqual(comparison['missingGenerations'], 1)
        pair = comparison['pairs'][0]
        self.assertEqual(pair['pairedCriteria'][0]['fullMinusReference'], 1)
        self.assertEqual(pair['arms']['baseline']['generationMetrics']['costUSD'],
                         {'status': 'unavailable', 'value': None})
        self.assertEqual(pair['arms']['full']['generationMetrics']['costUSD']['value'], 0.0)
        self.assertEqual(pair['arms']['full']['activation'][0]['results'][0]['passed'], True)
        self.assertIsNone(comparison['pairs'][1]['pairedCriteria'][0]['fullMinusReference'])

    def test_models_must_resolve_identically_before_delta(self):
        plan = self.plan()
        for resolved, status in ((None, 'unavailable'), ('different-model', 'incomparable')):
            pair = ablation.compare(plan, [self.observation(plan),
                self.observation(plan, 'baseline', False, resolved=resolved)])['pairs'][0]
            self.assertEqual(pair['modelComparability'], status)
            self.assertIsNone(pair['pairedCriteria'][0]['fullMinusReference'])

    def test_judge_failure_and_unjudged_generation_never_pass(self):
        plan = self.plan()
        bundle, judged = self.observation(plan)
        failed = copy.deepcopy(judged)
        failed.pop('inputSha256')
        failed['passed'] = False
        failed['results'][0].update(passed=False, error='', exitCode=1)
        failed = judge.seal(failed)
        result = ablation.compare(plan, [(bundle, failed)])['pairs'][0]['arms']['full']
        self.assertTrue(result['judgeError'])
        self.assertEqual(result['criteria'], {})
        self.assertEqual(ablation.compare(plan, [(bundle, None)])['pairs'][0]['arms']['full']['criteria'], {})

    def test_tampering_duplicates_wrong_judge_and_provenance_rejected(self):
        plan = self.plan()
        bundle, judged = self.observation(plan)
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            ablation.compare(plan, [(bundle, judged)] * 2)
        for field, value in (('response', 'tampered'), ('inputSha256', 'invalid')):
            bad = {**bundle, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                ablation.compare(plan, [(bad, judged)])
        bad = {k: v for k, v in judged.items() if k != 'inputSha256'}
        bad['canonicalModel'] = 'unregistered-judge'
        with self.assertRaisesRegex(ValueError, 'Canonical'):
            ablation.compare(plan, [(bundle, judge.seal(bad))])
        legacy = {k: v for k, v in bundle.items() if k != 'inputSha256'}
        legacy['provenance'] = None
        with self.assertRaisesRegex(ValueError, 'Unpinned'):
            ablation.compare(plan, [(judge.seal(legacy), judged)])

    def test_source_drift_and_symlinks_fail_without_changing_source(self):
        plan = self.plan()
        self.write(self.app / 'main.py', 'changed')
        with self.assertRaisesRegex(ValueError, 'source changed'):
            ablation.prepare(plan, 'full', 'rollback', 0, self.base / 'generation', self.base / 'record.json')
        self.assertFalse((self.base / 'generation').exists())
        (self.app / 'link.py').symlink_to(self.app / 'main.py')
        with self.assertRaisesRegex(ValueError, 'Symlink'):
            self.plan()

    def test_output_overlap_no_overwrite_and_failed_copy_cleanup(self):
        plan = self.plan()
        for target, record in ((self.app / 'out', self.base / 'record.json'),
                               (self.base / 'out', self.repo / 'record.json'),
                               (self.base / 'out', self.base / 'out/provenance.json')):
            with self.subTest(target=target, record=record), self.assertRaises(ValueError):
                ablation.prepare(plan, 'full', 'rollback', 0, target, record)
        target, record = self.base / 'out', self.base / 'record.json'
        with patch.object(ablation, 'copy_files', side_effect=ValueError('simulated drift')):
            with self.assertRaises(ValueError):
                ablation.prepare(plan, 'full', 'rollback', 0, target, record)
        self.assertFalse(target.exists())
        self.assertFalse(record.exists())
        ablation.prepare(plan, 'full', 'rollback', 0, target, record)
        original = record.read_text()
        with self.assertRaises(ValueError):
            ablation.prepare(plan, 'full', 'rollback', 0, self.base / 'other', record)
        self.assertEqual(record.read_text(), original)
        with self.assertRaises(FileExistsError):
            judge.write_new(record, {})

    def test_preregistered_ceilings_missing_usage_and_invalid_numbers(self):
        ceiling = ablation.ceilings()
        ceiling['generation']['inputTokens'] = 100
        ceiling['judging']['costUSD'] = 1
        plan = self.plan(metric_ceilings=ceiling)
        result = ablation.compare(plan, [self.observation(plan)])['pairs'][0]['arms']['full']['ceilings']
        self.assertIs(result['generation']['inputTokens']['passed'], False)
        self.assertIsNone(result['judging']['costUSD']['passed'])
        for value in (-1, True, float('nan'), float('inf')):
            with self.subTest(value=value), self.assertRaises(ValueError):
                judge.metrics({'costUSD': value})
        with self.assertRaises(ValueError):
            self.plan(runs=0)
        with self.assertRaises(ValueError):
            ablation.plan(self.repo, self.app, ['../escape'], ['fastapi-testing'],
                          model='m', effort='high', host_version='h', canonical_judge='j',
                          generation_timeout=30, max_turns=3)

    def test_prompt_grader_and_invocation_drift_refuse_freeze(self):
        plan = self.plan()
        provenance = ablation.preparation(plan, 'full', 'rollback', 0)
        for key in ('modelRequested', 'effort', 'claudeVersion', 'executionLimits'):
            report = copy.deepcopy(self.report)
            report[key] = 'changed'
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, 'invocation'):
                judge.freeze(report, 'rollback', self.case, variant='full', provenance=provenance)
        self.write(self.case / 'graders/quality.md', '---\ntype: llm\n---\nRelaxed criterion.')
        with self.assertRaisesRegex(ValueError, 'context'):
            judge.freeze(self.report, 'rollback', self.case, variant='full', provenance=provenance)

    def test_failed_generation_with_empty_diagnostic_cannot_be_frozen(self):
        for failure in ({'error': ''}, {'is_error': True}, {'exitCode': 1}):
            report = copy.deepcopy(self.report)
            report['cases'][0]['arms']['with'][0].update(failure)
            with self.subTest(failure=failure), self.assertRaisesRegex(ValueError, 'failed generation'):
                judge.freeze(report, 'rollback', self.case)

    def test_activation_only_case_needs_no_quality_judge(self):
        (self.case / 'graders/quality.md').unlink()
        plan = self.plan()
        provenance = ablation.preparation(plan, 'full', 'rollback', 0)
        bundle = judge.freeze(self.report, 'rollback', self.case, variant='full', provenance=provenance)
        result = ablation.compare(plan, [(bundle, None)])
        self.assertEqual(result['pairs'][0]['pairedCriteria'], [])
        self.assertEqual(bundle['criteria'], [])
        with patch.object(judge.subprocess, 'run') as call, self.assertRaisesRegex(ValueError, 'No quality'):
            judge.judge(bundle, 'model')
        call.assert_not_called()


if __name__ == '__main__':
    unittest.main()
