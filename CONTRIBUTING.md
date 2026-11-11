# Contributing

Read AGENTS.md and docs/architecture.md before executable changes. This repository
distributes a FastAPI plugin; skills/ and agents/ are product components. Requested
maintenance coordination uses docs/skills/repo-director/SKILL.md.

Runtime discovery and coordinated execution belong in runtime/. Hooks and MCP
delegate to it. Static inspection does not import application code; checks do not
install dependencies. Keep agent tool boundaries and application conventions.
Use Conventional Commits and a PR for normal maintenance changes.

## Language

Use English for repository documentation, instructions, code comments, user-facing
messages, metadata, commit messages, release notes and attached validation reports.
Preserve names, identifiers and quoted source material where translation would
change their meaning. Maintainer conversations may use the user's language.

## Validation

```bash
npm ci
node --check mcp-server/index.js
python3 -m py_compile runtime/*.py hooks/scripts/hook-runtime.py
# Project-creating fixtures use TMPDIR (default /var/tmp): choose an existing
# writable directory outside any Python project/workspace. Runtime state does not use it.
export TMPDIR=/var/tmp
bash tests/run-all.sh
npm audit --omit=dev
claude plugin validate . --strict
claude plugin validate skills --strict
claude plugin validate agents --strict
claude plugin validate docs/skills --strict
git diff --check
```

package.json and package-lock.json live at the repository root (Claude Code installs
marketplace dependencies only from the plugin root); mcp-server/package.json only
marks ESM. Run the suites with Python 3.11 as well when the runtime changes.
Prepare example dependencies in an isolated environment and run
`EXAMPLES_PYTHON=/absolute/environment/bin/python bash tests/examples/check.sh`.
Prepare the real ecosystem fixtures separately:

```bash
uv venv .fastapi-tools/validation-env
uv pip install --python .fastapi-tools/validation-env/bin/python -r tests/python-ecosystem/requirements.txt -r tests/examples/requirements.txt
EXAMPLES_PYTHON="$PWD/.fastapi-tools/validation-env/bin/python" bash tests/examples/check.sh
ECOSYSTEM_PYTHON="$PWD/.fastapi-tools/validation-env/bin/python" bash tests/python-ecosystem/check.sh
```

The fixture preparation may download dependencies; checks never install them.

Run `python3 scripts/install-doctor.py --workspace /path/to/application --project /path/to/application`
and the optional Codex protocol/installation smokes described in docs/codex.md.
They use temporary host state and make no model calls.

Behavioral evaluations require a separate explicit budget and authorization.
Functional fixtures do not establish measured skill or agent benefit. Record the
actual platform, versions and limitations; do not claim an unrun compatibility matrix.

## Publication

Align the plugin, marketplace, Codex manifest, root package, lock and MCP server
versions (`tests/repository` checks them, the metadata fields and the documented
counts). Update catalogs and evidence when
components change. Follow docs/releases.md and preserve unrelated work.

GitHub Actions and automatic Dependabot updates are disabled for this repository.
Keep vulnerability alerts, secret scanning and branch protections. Application CI
templates remain available. Never publish environments, node_modules, local state,
credentials or model reports. See docs/validation.md for release evidence.
