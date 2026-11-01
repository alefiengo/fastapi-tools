# Behavioral evaluations

Prompts and explicit graders cover FastAPI routing, authorization, async behavior,
Alembic history, deployment, evidence-based performance and test-writer scope.
They are model evaluations, separate from deterministic executable regressions.

Run only with explicit authorization and a budget: they require Claude
authentication and paid model calls. Offline harness tests do not make model calls.

```bash
claude plugin eval . --trust-plugin --case test-writer-behavior --runs 1 --ablation none --threshold 1 --no-publish
```

Fixture context is embedded in the test-writer prompt and checked for drift.
Keep generated reports in ignored evals/results/. Do not claim an evaluation pass
from unit tests validating this harness.

Freeze one complete response to compare judges against identical evidence:

```bash
python3 evals/tools/frozen_judge.py freeze evals/results/report.json evals/test-writer-behavior evals/results/frozen.json
python3 evals/tools/frozen_judge.py judge evals/results/frozen.json evals/results/judged.json --models YOUR_CANONICAL_MODEL --authorize-paid --max-budget-usd YOUR_AUTHORIZED_BUDGET
```

Choose the canonical model before seeing judgments. The tool verifies checksums,
explicit criteria and verbatim evidence lines. Preserve failed runs and diagnostics;
never overwrite earlier evidence or silently relax release criteria.

Offline `plan`, `prepare`, `freeze` and `compare` make no model calls. See the
[methodology](../docs/evaluation-methodology.md) for snapshots, three-arm
ablation, canonical judging, unavailable telemetry and limitations. The
[component inventory](../docs/component-evidence.json) covers every skill/agent.

```bash
bash tests/evaluations/test-basic.sh
```

Activation graders are independent of quality graders. A false-activation check
uses `min: 0`, `max: 0`, `arm: both`; a quality answer cannot establish that no
skill was invoked. The initializer cases cover authorization and protected paths;
real generation additionally requires the installed MCP tool schema, explicit
tool grants and runtime dependencies. Without those, its positive case only
checks handling of unavailable capabilities, never successful scaffolding.

The checked-in two-arm report is explicitly synthetic regression data. It is
not a paid evaluation result, a measured component benefit or a release gate.
