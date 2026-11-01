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
npm ci --prefix mcp-server
node --check mcp-server/index.js
python3 -m py_compile runtime/*.py hooks/scripts/hook-runtime.py
# Use an existing writable temporary directory outside a project/workspace.
export TMPDIR=/var/tmp
bash tests/run-all.sh
npm audit --prefix mcp-server --omit=dev
claude plugin validate . --strict
claude plugin validate skills --strict
claude plugin validate agents --strict
git diff --check
```

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

Align the plugin, marketplace, package, lock and MCP server versions. Include the
Codex manifest and doctor guard when present. Update catalogs and evidence when
components change. Follow docs/releases.md and preserve unrelated work.

GitHub Actions and automatic Dependabot updates are disabled for this repository.
Keep vulnerability alerts, secret scanning and branch protections. Application CI
templates remain available. Never publish environments, node_modules, local state,
credentials or model reports. See docs/validation.md for release evidence.
