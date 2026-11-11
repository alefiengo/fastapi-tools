"""The evidence inventory must cover the shipped components without efficacy claims."""
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = json.loads((ROOT / '.claude-plugin/plugin.json').read_text())['name']


def frontmatter(path):
    """Flat `key: value` frontmatter used by graders, prompts, skills and agents."""
    text = path.read_text()
    if not text.startswith('---\n'):
        return {}
    fields = {}
    for line in text.split('---', 2)[1].splitlines():
        key, sep, value = line.partition(':')
        if sep and not line.startswith(' '):
            fields[key.strip()] = value.strip().strip("'")
    return fields


def graders(case):
    return {path.stem: frontmatter(path) for path in (ROOT / 'evals' / case / 'graders').glob('*.md')}


def activates(grader, kind, name):
    """True only for a grader whose tool and input pattern select this exact component."""
    tool, key = ('Skill', 'skill') if kind == 'skill' else ('Agent', 'subagent_type')
    if grader.get('type') != 'tool_used' or grader.get('tool') != tool or 'input_match' not in grader:
        return False
    pattern = re.compile(grader['input_match'])
    return any(pattern.search(json.dumps({key: value})) for value in (name, f'{PLUGIN}:{name}'))


def false_activation(grader):
    return (grader.get('type') == 'tool_used' and grader.get('min') == '0'
            and grader.get('max') == '0' and grader.get('arm') == 'both')


class ComponentInventoryTests(unittest.TestCase):
    def setUp(self):
        self.inventory = json.loads((ROOT / 'docs/component-evidence.json').read_text())
        self.entries = self.inventory['components']
        self.components = {e['id']: e for e in self.entries}

    def test_complete_inventory_tracks_current_sources_and_existing_evidence(self):
        actual = {p.relative_to(ROOT).as_posix(): p for p in (
            *ROOT.glob('skills/*/SKILL.md'), *ROOT.glob('agents/*.md'))}
        self.assertEqual(len(self.entries), len(self.components))
        self.assertEqual({e['path'] for e in self.entries}, set(actual))
        self.assertEqual(self.inventory['paidEvaluationsRun'], 0)
        for entry in self.entries:
            with self.subTest(component=entry['id']):
                path = actual[entry['path']]
                self.assertEqual(entry['sourceSha256'], hashlib.sha256(path.read_bytes()).hexdigest(),
                                 'Refresh evidence after changing the component')
                self.assertTrue(entry['trigger'].strip())
                self.assertEqual(entry['behavioralEvidence']['status'], 'not-measured')
                self.assertEqual(entry['behavioralEvidence']['observedGenerations'], 0)
                self.assertIsNone(entry['behavioralEvidence']['effectSize'])
                functional = entry['functionalEvidence']
                # Structural-only components cite no tests instead of citing this inventory test.
                self.assertEqual(functional['status'] == 'structural-only', not functional['paths'])
                self.assertNotIn('tests/evaluations/component_inventory_test.py', functional['paths'])
                for evidence in functional['paths']:
                    self.assertTrue((ROOT / evidence).is_file(), evidence)
                for case in entry['behavioralEvidence']['cases'] + entry['negativeCases']:
                    self.assertTrue((ROOT / 'evals' / case / 'prompt.md').is_file(), case)
                    self.assertTrue(graders(case), case)
        groups = {g['id']: g for g in self.inventory['redundancyReview']}
        for entry in self.entries:
            for name in entry['redundancyGroups']:
                self.assertIn(entry['id'], groups[name]['members'])

    def test_roles_preserve_product_tool_boundaries(self):
        for path in ROOT.glob('agents/*.md'):
            tools = set(frontmatter(path)['tools'].split(', '))
            expected = {'Read', 'Glob', 'Grep'}
            # Only the test writer edits files; design agents return documents in their response.
            if path.stem == 'fastapi-test-writer':
                expected |= {'Write', 'Edit'}
            self.assertEqual(tools, expected, path.name)

    def test_every_component_has_an_observable_activation_criterion(self):
        for entry in self.entries:
            with self.subTest(component=entry['id']):
                skill_path = ROOT / entry['path']
                if entry['kind'] == 'skill' and frontmatter(skill_path).get('disable-model-invocation') == 'true':
                    # The model cannot call the Skill tool for it; a case must invoke it as the user.
                    prompts = [(ROOT / 'evals' / c / 'prompt.md').read_text().split('---', 2)[2].lstrip()
                               for c in entry['behavioralEvidence']['cases']]
                    self.assertTrue(any(p.startswith(f'/{PLUGIN}:{entry["id"]} ') for p in prompts))
                    continue
                found = [g for case in entry['behavioralEvidence']['cases']
                         for g in graders(case).values() if activates(g, entry['kind'], entry['id'])]
                self.assertTrue(found, 'needs a tool_used grader that selects this exact component')

    def test_activation_matching_is_exact_and_typed(self):
        reviewer = {'type': 'tool_used', 'tool': 'Agent',
                    'input_match': '"subagent_type"\\s*:\\s*"(?:[\\w-]+:)?fastapi-docker-reviewer"'}
        self.assertFalse(activates(reviewer, 'skill', 'fastapi-docker'))
        self.assertFalse(activates(reviewer, 'agent', 'fastapi-docker'))
        self.assertTrue(activates(reviewer, 'agent', 'fastapi-docker-reviewer'))

    def test_agent_activation_is_not_scored_without_the_plugin(self):
        # The host excludes only tool_used Skill graders from the without-arm by default.
        for path in ROOT.glob('evals/*/graders/*.md'):
            grader = frontmatter(path)
            if grader.get('tool') == 'Agent' and not false_activation(grader):
                self.assertEqual(grader.get('arm'), 'with-only', path.relative_to(ROOT))

    def test_model_invocable_skills_have_false_activation_cases(self):
        for entry in self.entries:
            if entry['kind'] != 'skill' or frontmatter(ROOT / entry['path']).get('disable-model-invocation') == 'true':
                continue
            with self.subTest(component=entry['id']):
                self.assertTrue(entry['negativeCases'])
                for case in entry['negativeCases']:
                    checks = [g for g in graders(case).values() if false_activation(g)]
                    self.assertTrue(any(activates({**g, 'min': None}, 'skill', entry['id']) for g in checks), case)
                    self.assertTrue(any(g.get('tool') == 'Agent' for g in checks), case)


if __name__ == '__main__':
    unittest.main()
