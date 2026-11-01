# Evaluation methodology and evidence

The [inventory](component-evidence.json) covers every distributed skill and agent:
trigger, reviewed-text hash, related regressions, prospective cases and overlaps.
**Behavioral benefit: NOT MEASURED.** No paid evaluations or model generations ran.
A correct example, activation grader or integration smoke does not establish that
a component improves responses.

## What the evidence establishes

| Signal | Supported conclusion | Still unverified |
| --- | --- | --- |
| Frontmatter, reference and permission integrity | The component is inventoried and retains its declared surface | Actual loading in each host |
| Deterministic harness tests | Consistent preparation/comparison under synthetic fixtures | Skill/agent effectiveness |
| Real FastAPI/Pydantic/SQLAlchemy/Alembic examples | Specific behaviors executed in that environment | PostgreSQL, load, all version ranges |
| `tool_used` | Activation observed in a real transcript, if run | Quality or causality |
| Quality rubric applied to a frozen response | Per-criterion result for that sample and judge | Generalization and causal comparison |
| Full versus baseline/selected-minus | Paired differences under equivalent inputs | Benefit when arms, isolation or actual model identity are missing |

The inventory's functional fields point to available tests; they do not assert
that a model executed each component. Sources and checksums detect drift; they
neither authenticate a run nor replace its logs.

## Official sources consulted before decisions

- [Claude plugin evals](https://code.claude.com/docs/en/plugin-evals): distinguishes
  activation/quality, grants, mocks, scaffolds and real MCP servers.
- [Skills](https://code.claude.com/docs/en/skills) and
  [agents](https://code.claude.com/docs/en/sub-agents): frontmatter and tools are
  part of the product.
- [CLI](https://code.claude.com/docs/en/cli-reference): the spending limit is an
  estimate that can be exceeded, not an exact billing guarantee.
- [FastAPI async tests](https://fastapi.tiangolo.com/advanced/async-tests/): HTTPX
  does not start lifespan automatically.
- [Pydantic migration](https://docs.pydantic.dev/latest/migration/): nullable does
  not mean omittable in v2; a validator's TypeError does not become ValidationError.
- [SQLAlchemy sessions](https://docs.sqlalchemy.org/en/20/orm/session_basics.html)
  and [asyncio](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html):
  rollback after failed flush, one session per task and explicit relationship loading.
- [Alembic autogenerate](https://alembic.sqlalchemy.org/en/latest/autogenerate.html):
  manual review, rename-detection limits and the executable scope of check.

## Offline ablation

`evals/tools/ablation.py` provides only `plan`, `prepare` and `compare`: it runs no
models, builds, installations or network operations. The plan fixes host/version,
requested model, effort, canonical judge, turn/time limits, repetitions, prompts,
all graders, snapshots and removed components. It uses three variants:

- `baseline`: the same project, without the plugin.
- `full`: the complete project and product for the Claude Code experiment.
- `selected-minus`: the same product with only the selected skills/agents removed.

Remove a single component to isolate its contribution; removing a skill and agent
together measures the combined intervention. A prepared snapshot does not establish
actual plugin loading or MCP dependency availability. This harness is designed for
Claude Code; it does not measure Codex behavior.

```bash
python3 evals/tools/ablation.py plan /tmp/fastapi-eval-plan.json \
  --snapshot /tmp/fastapi-fixture --cases test-writer-behavior \
  --model EXACT_GENERATOR_ID --effort high --host-version EXACT_HOST_VERSION \
  --canonical-judge EXACT_JUDGE_ID --generation-timeout 300 --max-turns 10 \
  --minus fastapi-testing fastapi-test-writer
python3 evals/tools/ablation.py prepare /tmp/fastapi-eval-plan.json /tmp/fastapi-eval-full \
  --variant full --case test-writer-behavior --record /tmp/fastapi-eval-full-provenance.json
python3 evals/tools/ablation.py compare /tmp/fastapi-eval-plan.json /tmp/fastapi-eval-pending.json
```

The application snapshot must be explicit and separate from the plugin checkout.
Prepare each arm in a fresh, absent destination. Operator records stay outside
both source trees and the generation tree. The latter contains only `workspace/`
and, where applicable, `plugin/`. Contents and executable bits are preserved;
included symlinks and special files are rejected, and drift is checked before
copying. Maintenance instructions AGENTS/CLAUDE/GEMINI, evals, graders, reports,
docs, environments, caches, `.env*` credentials and generated dependencies are
excluded at any depth. Inspect the included files: filtering is not a universal
detector of secrets or answer leakage.

An authorized external runner must enforce actual tool and filesystem isolation,
disable ambient instructions/plugins, supply the same prompt/context to every arm
and record actual loading. Fresh directories and hashes do not stop an unrestricted
tool from reading neighboring trees. Graders/records must never be exposed to the
generator. The test-writer case embeds its context; a regression checks that it
matches the fixtures.

## Freeze, judge and compare

The freezer preserves compatibility with arm `with`, run 0; it accepts `--arm`,
`--variant` and `--provenance`. It requires the current prompt and freezes grader
definitions. For paired comparisons, it verifies that the report declares
`modelRequested`, `effort`, `claudeVersion` and `executionLimits` matching the
preparation. An older report without provenance can be judged separately but
cannot establish retrospective equivalence. Actual arguments are not inferred
from the plan.

```bash
python3 evals/tools/frozen_judge.py freeze /tmp/generation.json \
  evals/test-writer-behavior /tmp/full-frozen.json --arm with --variant full \
  --provenance /tmp/fastapi-eval-full-provenance.json
python3 evals/tools/ablation.py compare /tmp/fastapi-eval-plan.json /tmp/fastapi-eval-comparison.json \
  --entry /tmp/full-frozen.json /tmp/full-judged.json \
  --entry /tmp/baseline-frozen.json /tmp/baseline-judged.json
```

Use `-` as the second argument to `--entry` to retain an unjudged generation.
The `judge` command is external and paid; it requires explicit authorization and
budget, plus `--authorize-paid --max-budget-usd`. The estimated budget is divided
among the requested judges; leave room for possible CLI overruns. No offline
operation automatically invokes `judge`.

The judge receives only the prompt, criteria and frozen-response lines: no arm
identity, prior scores or generation metadata. It runs from an empty temporary
cwd with tools/MCP disabled. Each criterion needs a boolean, reason and nonempty
literal evidence line for PASS. Omissions/failures remain failures; an invocation
error never becomes a quality pass. The preregistered first judge is canonical.
Additional judges are diagnostic.

Comparison preserves per-sample criteria, separate activation, generation/judging
telemetry and missing arms. Tokens/cost/duration come only from the result that
declares them, never report totals that might include graders. Missing fields are
`unavailable`, not zero; a declared zero remains a value. Different resolved models
produce `incomparable`; no delta is calculated without resolved identity. Optional
ceilings are preregistered in JSON with generation/judging and
inputTokens/outputTokens/costUSD/durationMs; `null` means not registered, and a
missing metric cannot pass a ceiling.

All reports are created without overwriting. SHA-256 seals detect accidental
changes; someone can recompute them over fabricated evidence. Keep original reports
and trustworthy logs. The harness does not automatically assert effectiveness,
statistical significance or token/cost savings.

## Initializer evaluation

The verified contract is
`initialize_project({destination, projectName, explicitRequest: true})`, delegating
to CLI `action: initialize`. The skill checks the actually installed schema; it
does not invent options or a final response. It requires an absent destination,
explicit authorization and protection of Python/workspace ancestors. Empty
directories and dangling symlinks are existing destinations. Generation is separate
from dependency installation, execution, migrations, Git and publication.

Three cases cover positive authorization, protected ancestors/destinations and
preview without authorization. Without a real tool or grant, the positive case
only evaluates handling of that limitation. A future real functional evaluation
needs the host's exact tool permissions, MCP dependencies and an authorized
scaffold; `--trust-plugin` alone does not grant those accesses. Runtime/MCP checks
verify initializer implementation separately.

## Harness coverage and redundancy

| Inspected trigger | Finding/correction | Main files |
| --- | --- | --- |
| Compare a component with its absence | Added plan, preparation without leakage and offline paired comparison | evals/tools/ablation.py, tests/evaluations/ablation_test.py |
| Rejudge a report | Added per-arm provenance, separate metrics and judge blinding | evals/tools/frozen_judge.py, tests/evaluations/judge_test.py |
| Claim catalog coverage/benefit | Added individual evidence; separated activation from quality | docs/component-evidence.json, tests/evaluations/component_inventory_test.py, evals/*/graders/ |
| Create a new project | Added a skill matching the new MCP contract and destination limits | skills/fastapi-initializer/SKILL.md, evals/initializer-*/ |
| Failed flush/apparent rollback | Mocks or teardown can hide missing atomicity; require real writes and an independent observer | skills/fastapi-testing/, skills/fastapi-database/, agents/fastapi-runtime-reviewer.md, tests/examples/test_sqlalchemy.py |
| Alembic check/autogenerate | Neither equals AST lint nor proves safe renames/backfills | skills/fastapi-database/, agents/fastapi-migration-reviewer.md, tests/examples/test_alembic.py |
| Pydantic migration | Required/null, TypeError and lazy ORM need wire-level tests | skills/fastapi-pydantic-v1-to-v2-migration/, tests/examples/test_pydantic_async.py |
| Check module boundaries | Avoid imposing import-linter when it is not configured | skills/fastapi-modular-architecture/ |

All existing components are retained. The inventory's redundancy review records
members, output/permission distinctions and decisions. Overlaps exist between
design/implementation, test guidance/writer, database/reviewers, performance/load,
architecture/designer and Docker/CI/reviewer. These are ablation candidates, not
evidence for removal. Product permissions are described in agent definitions.

## Validation and limits

```bash
bash tests/evaluations/test-basic.sh
EXAMPLES_PYTHON=.fastapi-tools/validation-env/bin/python bash tests/examples/check.sh
git diff --check -- skills agents evals tests/evaluations tests/examples \
  docs/component-evidence.json docs/evaluation-methodology.md
```

Examples include routers/OpenAPI, filtered responses, overrides, lifespan, Pydantic
v2 errors, real SQLAlchemy rollback and Alembic against temporary SQLite. They do
not test PostgreSQL, actual AsyncSession concurrency or a complete version matrix.
Functional tests, real examples and host smokes establish integration, not measured
behavioral benefit. The inventory attributes no measured benefit to any skill or
agent.

See [validation](validation.md) for release commands, environment and limits.
