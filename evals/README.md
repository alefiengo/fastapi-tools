# Behavioral evaluations

Prompts and explicit graders cover FastAPI routing, authorization, async behavior,
Alembic history, deployment, evidence-based performance and test-writer scope.
They are model evaluations, separate from deterministic executable regressions.

Run only when requested: they require Claude authentication and paid model calls.

```bash
claude plugin eval . --trust-plugin --case test-writer-behavior --runs 1 --ablation none --threshold 1 --no-publish
```

Fixture context is embedded in the test-writer prompt and checked for drift.
Keep generated reports in ignored evals/results/. Do not claim an evaluation pass
from unit tests validating this harness.

Freeze one complete response to compare judges against identical evidence:

```bash
python3 evals/tools/frozen_judge.py freeze evals/results/report.json evals/test-writer-behavior evals/results/frozen.json
python3 evals/tools/frozen_judge.py judge evals/results/frozen.json evals/results/judged.json --models YOUR_CANONICAL_MODEL
```

Choose the canonical model before seeing judgments. The tool verifies checksums,
explicit criteria and verbatim evidence lines. Preserve failed runs and diagnostics;
never overwrite earlier evidence or silently relax release criteria.
