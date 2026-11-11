# Evaluation methodology and evidence

The [inventory](component-evidence.json) covers every distributed skill and agent:
trigger, reviewed-text hash, related regressions (or `structural-only` when none
exercises the guidance), prospective cases, false-activation cases and overlaps.
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

## Activation, mocks and negatives

Verified on 2026-11-11 against the plugin-evals documentation and the Claude Code
2.1.322 grader implementation:

- Only `tool_used` graders whose tool is `Skill` leave the without-arm score by
  default. Positive `Agent` activation graders therefore set `arm: with-only`;
  otherwise the baseline, which cannot dispatch plugin agents, inflates the delta.
- `tool_used` compares the tool name exactly. Plugin MCP tools are named
  `mcp__plugin_fastapi-tools_fastapi__<tool>`.
- A run never starts the plugin's MCP server unless asked, and an unmocked tool
  is absent, so a "never called" check on it passes trivially. Cases that depend
  on MCP tools carry `mocks/fastapi/<tool>.md`; `evals/mocks/fastapi/_tools.json`
  is the server's real `tools/list` result. Mock bodies are real responses from
  local fixtures, with local paths replaced. A regression compares the catalog
  with the live server and checks mock names, `expect:` keys and MCP graders.
- `expect:` literals are compared as strings: quote booleans (`"true"`) and
  write a path that starts with `/` as a one-element list so it is not read as
  a `/regex/`.
- `fastapi-pr-review` sets `disable-model-invocation`, which blocks the Skill
  tool. Its case starts with `/fastapi-tools:fastapi-pr-review`; how a
  user-invoked skill appears in the transcript was not verified, so the case
  has no Skill activation grader.
- Each model-invocable skill lists near-miss `negativeCases` (plain pytest,
  SQLAlchemy batch jobs, Flask JWT, Django images, CLI import cycles, asyncio
  programs, Celery observability) with `min: 0`, `max: 0`, `arm: both` checks.
- Criteria about tool use the judge cannot see (the default focus is the final
  message) are deterministic `tool_used` graders, not rubric text.

## Offline ablation

`evals/tools/ablation.py` provides only `plan`, `prepare` and `compare`: it runs no
models, builds, installations or network operations. The plan fixes host/version,
requested model, effort when controlled, canonical judge, turn/time limits, repetitions, prompts,
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
  --model EXACT_GENERATOR_ID --host-version EXACT_HOST_VERSION \
  --canonical-judge EXACT_JUDGE_ID --generation-timeout 300 --max-turns 12 \
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
copying. Maintenance instructions AGENTS/CLAUDE/GEMINI, environments, caches,
`.env*` credentials and generated dependencies are excluded at any depth.
Application directories such as `docs/`, `reports/` or `results/` are kept; an
application snapshot containing an `evals/` or `graders/` directory is refused
rather than silently filtered. The plugin copy includes `evals/` except
`evals/results/`, so `claude plugin eval` finds the suite in a prepared arm; the
host hides the eval directory from the agent under test. Inspect the included
files: filtering is not a universal detector of secrets or answer leakage.

With `claude plugin eval`, the runnable mapping is: `full` and `baseline` are the
with-arm and without-arm of `claude plugin eval <arm>/plugin --case <case>
--ablation with-without`; `selected-minus` is `claude plugin eval
<selected-minus>/plugin --case <case> --ablation none`. The host has no effort
option, so `--effort` is optional and recorded as `null` when not controlled.
`--generation-timeout` and `--max-turns` must equal each case's `prompt.md`
frontmatter (`timeout_seconds`, default 300; `max_turns`, default 10), which is
what the host applies. Each run starts in an empty workspace, so the
`workspace/` snapshot is provenance only until a case uses a scaffold script.
Mocks replace the MCP server, so the plugin copy needs no `node_modules`. This
mapping and the report fields that `freeze` reads (`promptMarkdown`, `response`,
`modelRequested`, `executionLimits`) have not been validated with a paid run:
the only report in the repository is synthetic.

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
preparation; `effort` is compared only when the plan pinned it. An older report
without provenance can be judged separately but
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
preview without authorization. Their mocks return real `initialize_project`
responses: the positive mock guards the exact destination, project name and
`explicitRequest`, and a grader requires exactly one call; the preview case makes
the tool available and requires zero calls; the protected-ancestor mock returns
the runtime's real refusal. Mocks do not create files: runtime/MCP regressions
verify the initializer implementation separately.

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
| Observe plugin MCP tools in a run | Real-response mocks, saved catalog and exact-name graders | evals/mocks/, evals/*/mocks/, tests/evaluations/mock_contract_test.py |
| Score agent activation fairly | `arm: with-only` on positive Agent graders; typed exact matching | evals/*/graders/, tests/evaluations/component_inventory_test.py |
| Hijacking generic Python | FastAPI-scoped descriptions and near-miss negative cases | skills/*/SKILL.md frontmatter, evals/neg-*/ |
| Keep design agents read-only | Architect and API designer return documents; no Write/Edit | agents/, evals/architecture-design-scope/ |

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
