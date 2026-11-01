#!/usr/bin/env python3
"""Offline plan/prepare/compare for FastAPI components. Never invokes a model."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

from frozen_judge import body, definitions, digest, metrics, seal, validate, verify, write_new

PRODUCT = {'.claude-plugin', '.mcp.json', '.lsp.json', 'agents', 'skills', 'hooks',
           'runtime', 'mcp-server', 'scripts'}
EXCLUDE = {'.git', '.claude', '.codex', '.agents', '.fastapi-tools', '.venv', 'venv',
           'node_modules', '__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache',
           'evals', 'graders', 'reports', 'results', 'docs'}
INSTRUCTIONS = {'agents.md', 'claude.md', 'gemini.md'}
METRICS = ('inputTokens', 'outputTokens', 'costUSD', 'durationMs')
VARIANTS = ('baseline', 'full', 'selected-minus')


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]*', value):
        raise ValueError('Unsafe case/component identifier')
    return value


def inventory(root, *, product=False):
    if root.is_symlink():
        raise ValueError('Symlinked snapshot root')
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('Snapshot must be a directory')
    output = {}

    def walk(directory):
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(root)
            if (path.name in EXCLUDE or path.name.lower() in INSTRUCTIONS
                    or path.name.startswith('.env') or path.suffix == '.pyc'
                    or (product and relative.parts[0] not in PRODUCT)):
                continue
            if path.is_symlink():
                raise ValueError('Symlink in snapshot: ' + str(relative))
            if path.is_dir():
                walk(path)
            elif path.is_file():
                output[relative.as_posix()] = {
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                    'executable': bool(path.stat().st_mode & 0o111)}
            else:
                raise ValueError('Special file in snapshot')
    walk(root)
    return output


def ceilings(value=None):
    if value is None:
        value = {stage: dict.fromkeys(METRICS) for stage in ('generation', 'judging')}
    if not isinstance(value, dict) or set(value) != {'generation', 'judging'}:
        raise ValueError('Ceilings need generation and judging')
    for stage in value.values():
        if not isinstance(stage, dict) or set(stage) != set(METRICS):
            raise ValueError('Specify every ceiling; null means not preregistered')
        if any(v is not None and (type(v) not in (int, float) or not math.isfinite(v) or v < 0)
               for v in stage.values()):
            raise ValueError('Invalid ceiling')
    return value


def plan(repo, snapshot, cases, minus, *, model, effort, host_version, canonical_judge,
         generation_timeout, max_turns, runs=1, metric_ceilings=None):
    if repo.is_symlink() or snapshot.is_symlink():
        raise ValueError('Use regular source directories')
    repo, snapshot = repo.resolve(strict=True), snapshot.resolve(strict=True)
    if snapshot == repo or snapshot.is_relative_to(repo) or repo.is_relative_to(snapshot):
        raise ValueError('Use a separate application snapshot outside the plugin tree')
    for value in (model, effort, host_version, canonical_judge):
        if not isinstance(value, str) or not value.strip():
            raise ValueError('Pin model, effort, host version and canonical judge')
    if any(type(v) is not int or v < 1 for v in (runs, generation_timeout, max_turns)):
        raise ValueError('Runs and execution limits must be positive integers')
    components = {p.parent.name: p.parent.relative_to(repo).as_posix()
                  for p in (repo / 'skills').glob('*/SKILL.md')}
    components.update({p.stem: p.relative_to(repo).as_posix() for p in (repo / 'agents').glob('*.md')})
    if not minus or len(set(minus)) != len(minus) or any(m not in components for m in minus):
        raise ValueError('Choose distinct existing skills/agents for selected-minus')
    if not cases or len(set(cases)) != len(cases):
        raise ValueError('Cases must be nonempty and unique')
    contexts = {}
    for name in cases:
        case = repo / 'evals' / identifier(name)
        if any(p.is_symlink() for p in (case, case / 'prompt.md', case / 'graders')):
            raise ValueError('Symlinked case input')
        contexts[name] = {'prompt': body(case / 'prompt.md'), 'criterionDefinitions': definitions(case)}
    project_files, plugin_files = inventory(snapshot), inventory(repo, product=True)
    if not project_files or any(Path(p).parts[0] in PRODUCT for p in project_files):
        raise ValueError('Supply application-only fixture files')
    return seal({'schemaVersion': 1, 'kind': 'ablation-plan',
                 'pluginSource': str(repo), 'projectSource': str(snapshot),
                 'projectFiles': project_files, 'pluginFiles': plugin_files,
                 'projectSnapshotSha256': digest(project_files), 'pluginSnapshotSha256': digest(plugin_files),
                 'cases': contexts, 'minus': {m: components[m] for m in minus}, 'runs': runs,
                 'variants': list(VARIANTS), 'modelRequested': model, 'effort': effort,
                 'claudeVersion': host_version, 'canonicalJudge': canonical_judge,
                 'executionLimits': {'timeoutSeconds': generation_timeout, 'maxTurns': max_turns},
                 'metricCeilings': ceilings(metric_ceilings), 'effectivenessClaim': None})


def variant_files(data, variant):
    if variant not in VARIANTS:
        raise ValueError('Unknown variant')
    if variant == 'baseline':
        return {}
    removed = data['minus'].values() if variant == 'selected-minus' else []
    return {p: h for p, h in data['pluginFiles'].items()
            if not any(p == r or p.startswith(r + '/') for r in removed)}


def preparation(data, variant, case, run):
    verify(data)
    if case not in data['cases'] or type(run) is not int or not 0 <= run < data['runs']:
        raise ValueError('Unknown case/run')
    return seal({'schemaVersion': 1, 'kind': 'ablation-preparation',
                 'planSha256': data['inputSha256'], 'variant': variant, 'case': case, 'run': run,
                 **data['cases'][case],
                 **{k: data[k] for k in ('modelRequested', 'effort', 'claudeVersion',
                     'canonicalJudge', 'executionLimits', 'projectSnapshotSha256', 'pluginSnapshotSha256')},
                 'variantSnapshotSha256': digest(variant_files(data, variant))})


def copy_files(source, destination, files):
    for relative, expected in files.items():
        path = Path(relative)
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Unsafe snapshot path')
        origin = source / path
        if any(p.is_symlink() for p in (origin, *origin.parents)):
            raise ValueError('Snapshot symlink introduced during copy')
        data = origin.read_bytes()
        if hashlib.sha256(data).hexdigest() != expected['sha256']:
            raise ValueError('Snapshot changed during copy')
        target = destination / path
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open('xb') as stream:
            stream.write(data)
        target.chmod(0o755 if expected['executable'] else 0o644)


def prepare(data, variant, case, run, destination, record_path):
    record = preparation(data, variant, case, run)
    source, plugin = Path(data['projectSource']), Path(data['pluginSource'])
    destination, record_path = destination.absolute(), record_path.absolute()
    resolved = destination.resolve()
    if any(resolved.is_relative_to(p) or p.is_relative_to(resolved) for p in (source, plugin)):
        raise ValueError('Preparation must be outside both source trees')
    if (record_path.exists() or record_path.is_symlink() or
            any(record_path.resolve().is_relative_to(p) for p in (resolved, source, plugin))):
        raise ValueError('Use a fresh operator record outside sources and generation tree')
    if inventory(source) != data['projectFiles'] or inventory(plugin, product=True) != data['pluginFiles']:
        raise ValueError('Pinned source changed; create a new plan')
    destination.mkdir(exist_ok=False)
    try:
        workspace = destination / 'workspace'
        workspace.mkdir()
        copy_files(source, workspace, data['projectFiles'])
        files = variant_files(data, variant)
        if files:
            product = destination / 'plugin'
            product.mkdir()
            copy_files(plugin, product, files)
        write_new(record_path, record)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return record


def compare(data, entries):
    verify(data)
    observed = {}
    for bundle, judged in entries:
        verify(bundle)
        provenance = bundle.get('provenance')
        if not isinstance(provenance, dict):
            raise ValueError('Unpinned legacy bundle cannot establish a comparison')
        expected = preparation(data, bundle['variant'], bundle['case'], bundle['generation']['run'])
        criteria = [{'id': d['id'], 'criterion': d['criterion']}
                    for d in expected['criterionDefinitions'] if d['type'] == 'llm']
        if (provenance != expected or bundle['prompt'] != expected['prompt']
                or bundle['criterionDefinitions'] != expected['criterionDefinitions'] or bundle['criteria'] != criteria):
            raise ValueError('Bundle differs from pinned preparation')
        key = (bundle['case'], bundle['generation']['run'], bundle['variant'])
        if key in observed:
            raise ValueError('Duplicate case/run/variant')
        quality, judge_metrics, error = {}, metrics({}), None
        if judged is not None:
            verify(judged)
            if judged.get('case') != bundle['case'] or judged.get('canonicalModel') != data['canonicalJudge']:
                raise ValueError('Canonical judge differs from plan')
            canonical = judged['results'][0]
            if canonical.get('inputSha256') != bundle['inputSha256'] or canonical.get('modelRequested') != data['canonicalJudge']:
                raise ValueError('Judge input/model mismatch')
            error = canonical.get('error')
            if 'error' in canonical or canonical.get('exitCode', 0) != 0:
                error = error or 'Judge invocation failed'
                if canonical.get('passed') is not False or judged.get('passed') is not False:
                    raise ValueError('Judge error cannot pass')
            else:
                passed = validate(bundle, canonical.get('judgments'))
                if canonical.get('passed') is not passed or judged.get('passed') is not passed:
                    raise ValueError('Inconsistent judge verdict')
                quality = {j['id']: j['passed'] for j in canonical['judgments']}
            judge_metrics = metrics(canonical.get('raw', {}))
            if canonical.get('metrics', judge_metrics) != judge_metrics:
                raise ValueError('Judge telemetry differs from raw output')
        generation_metrics = bundle['generation']['metrics']
        # Validate normalized telemetry, including seals recomputed over malformed data.
        for telemetry in (generation_metrics, judge_metrics):
            if set(telemetry) != {*METRICS, 'resolvedModel'}:
                raise ValueError('Missing telemetry dimensions')
            for name, item in telemetry.items():
                value = item['value']
                if item['status'] != ('unavailable' if value is None else 'reported'):
                    raise ValueError('Inconsistent telemetry status')
                if name == 'resolvedModel' and value is not None and (
                        not isinstance(value, str) or not value.strip()):
                    raise ValueError('Invalid resolved model')
                if name != 'resolvedModel' and value is not None and (
                        type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                    raise ValueError('Invalid telemetry value')
        gates = {}
        for stage, telemetry in (('generation', generation_metrics), ('judging', judge_metrics)):
            gates[stage] = {name: {'ceiling': ceiling, 'value': telemetry[name]['value'],
                'passed': telemetry[name]['value'] <= ceiling
                    if ceiling is not None and telemetry[name]['value'] is not None else None}
                for name, ceiling in ceilings(data['metricCeilings'])[stage].items()}
        observed[key] = {'criteria': quality, 'activation': bundle['activationResults'],
                         'generationMetrics': generation_metrics, 'judgingMetrics': judge_metrics,
                         'judgeError': error, 'ceilings': gates, 'frozenSha256': bundle['inputSha256']}
    pairs = []
    for case, context in data['cases'].items():
        for run in range(data['runs']):
            for reference in ('baseline', 'selected-minus'):
                arms = {v: observed.get((case, run, v)) for v in (reference, 'full')}
                statuses = []
                for stage in ('generationMetrics', 'judgingMetrics'):
                    values = [a[stage]['resolvedModel']['value'] if a else None for a in arms.values()]
                    statuses.append('unavailable' if None in values else 'matched' if len(set(values)) == 1 else 'incomparable')
                comparability = ('incomparable' if 'incomparable' in statuses else
                                 'unavailable' if 'unavailable' in statuses else 'matched')
                outcomes = []
                for criterion in context['criterionDefinitions']:
                    if criterion['type'] != 'llm':
                        continue
                    values = {v: a['criteria'].get(criterion['id']) if a else None for v, a in arms.items()}
                    available = all(type(v) is bool for v in values.values()) and comparability == 'matched'
                    outcomes.append({'id': criterion['id'], 'outcomes': values,
                        'fullMinusReference': int(values['full']) - int(values[reference]) if available else None})
                pairs.append({'case': case, 'run': run, 'reference': reference, 'arms': arms,
                              'modelComparability': comparability, 'pairedCriteria': outcomes})
    expected = len(data['cases']) * data['runs'] * len(VARIANTS)
    return seal({'schemaVersion': 1, 'kind': 'ablation-comparison', 'planSha256': data['inputSha256'],
                 'expectedGenerations': expected, 'observedGenerations': len(observed),
                 'missingGenerations': expected - len(observed), 'pairs': pairs,
                 'effectivenessClaim': None,
                 'interpretation': 'Offline/synthetic fixtures validate the harness; behavioral benefit is NOT MEASURED.'})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    p = sub.add_parser('plan')
    p.add_argument('output', type=Path)
    p.add_argument('--repo', type=Path, default=Path(__file__).resolve().parents[2])
    p.add_argument('--snapshot', type=Path, required=True)
    p.add_argument('--cases', nargs='+', required=True)
    p.add_argument('--minus', nargs='+', required=True)
    p.add_argument('--model', required=True)
    p.add_argument('--effort', required=True)
    p.add_argument('--host-version', required=True)
    p.add_argument('--canonical-judge', required=True)
    p.add_argument('--generation-timeout', type=int, required=True)
    p.add_argument('--max-turns', type=int, required=True)
    p.add_argument('--runs', type=int, default=1)
    p.add_argument('--ceilings', type=Path)
    p = sub.add_parser('prepare')
    p.add_argument('plan', type=Path)
    p.add_argument('destination', type=Path)
    p.add_argument('--record', type=Path, required=True)
    p.add_argument('--variant', choices=VARIANTS, required=True)
    p.add_argument('--case', required=True)
    p.add_argument('--run', type=int, default=0)
    p = sub.add_parser('compare')
    p.add_argument('plan', type=Path)
    p.add_argument('output', type=Path)
    p.add_argument('--entry', nargs=2, action='append', default=[], metavar=('FROZEN', 'JUDGED_OR_DASH'))
    args = parser.parse_args()
    if args.action == 'plan':
        result = plan(args.repo, args.snapshot, args.cases, args.minus, model=args.model,
                      effort=args.effort, host_version=args.host_version, canonical_judge=args.canonical_judge,
                      generation_timeout=args.generation_timeout, max_turns=args.max_turns, runs=args.runs,
                      metric_ceilings=json.loads(args.ceilings.read_text()) if args.ceilings else None)
    else:
        data = json.loads(args.plan.read_text())
        if args.action == 'prepare':
            prepare(data, args.variant, args.case, args.run, args.destination, args.record)
            return
        result = compare(data, [(json.loads(Path(b).read_text()),
                               None if j == '-' else json.loads(Path(j).read_text())) for b, j in args.entry])
    write_new(args.output, result)


if __name__ == '__main__':
    main()
