# Contributing

This repository distributes a plugin, not a FastAPI application. Read AGENTS.md
and docs/architecture.md first. Maintenance coordination is documented separately
in docs/skills/repo-director/SKILL.md; shipped skills/ and agents/ are product.
Keep FastAPI/Python conventions and applications’ existing tool choices. Read
official tool documentation before changing behavior; record sources and limits.
Reviewers use Read, Glob and Grep only; designers and test writers have scoped output.

Runtime discovery and coordinated execution belong in runtime/. MCP and hooks
must delegate. Static inspection never imports application modules. Checks never
install dependencies; initialization never runs checks or installs dependencies.
Align Claude/marketplace/Codex/package/lock/server versions on release. Update
catalogs and evidence references when adding, renaming or removing components.

## Local validation

```bash
npm ci --prefix mcp-server
node --check mcp-server/index.js
python3 -m py_compile runtime/*.py hooks/scripts/hook-runtime.py scripts/install-doctor.py
bash tests/run-all.sh
npm audit --prefix mcp-server --omit=dev
claude plugin validate . --strict
claude plugin validate skills --strict
claude plugin validate agents --strict
python3 scripts/install-doctor.py --plugin-root "$PWD" --workspace /path/to/trusted-application --project /path/to/trusted-application
git diff --check
```

Validate the maintenance skill’s YAML, directory name and references separately;
it is deliberately outside the shipped catalog.

Deterministic suites use temporary projects, controlled executables, stdio MCP
and local HTTP listeners. Add meaningful regressions for executable changes.
Run the real ecosystem separately; it requires explicit dependency preparation:

```bash
uv venv .fastapi-tools/validation-env
uv pip install --python .fastapi-tools/validation-env/bin/python -r tests/python-ecosystem/requirements.txt -r tests/examples/requirements.txt
EXAMPLES_PYTHON="$PWD/.fastapi-tools/validation-env/bin/python" bash tests/examples/check.sh
ECOSYSTEM_PYTHON="$PWD/.fastapi-tools/validation-env/bin/python" bash tests/python-ecosystem/check.sh
```

The optional preparation commands download dependencies; test execution does not
install them. Fixtures create isolated temporary environments and run actual
pytest/Ruff/mypy/Alembic through Python, uv and Poetry. See tests/python-ecosystem/README.md.
Record actual OS/tool versions, warnings and skipped checks. Linux evidence does
not establish macOS/WSL or a Node/Python matrix. Codex smoke tests must not make
model calls or modify account configuration. See docs/codex.md.

Behavioral evaluations need a separate explicit budget and authorization. The
offline harness only prepares or compares evidence: evals/README.md. Functional
checks do not establish model efficacy. Preserve failures and compare frozen
responses with the same judge when authorized evaluations are run.

## Contribution and publication

Use Conventional Commits, following repository history. PR descriptions explain
the resulting behavior, validation and material limits. Preserve unrelated work.
Inspect git status, remotes and GitHub settings before publication. The intended
repository is alefiengo/fastapi-tools; the sibling reference is read-only.

GitHub Actions and automatic Dependabot updates are disabled in this repository.
No Actions badge, workflow or required Actions status check belongs here. Keep
vulnerability alerts, secret scanning/push protection and PR/history/delete/force
push protections. This does not remove CI examples offered to user applications.
Use local validation and attach release evidence following docs/releases.md.
Never publish node_modules, environments, secrets, local state or model reports.
