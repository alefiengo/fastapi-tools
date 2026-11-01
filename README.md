# FastAPI Tools for Claude Code and Codex

[![Release](https://img.shields.io/github/v/release/alefiengo/fastapi-tools)](https://github.com/alefiengo/fastapi-tools/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A local plugin for developing and reviewing FastAPI applications: 16 shared skills
and seven MCP tools. Claude Code also registers seven specialist agents and five
hooks. Both hosts share Python discovery, process locks and verification records.
Project initialization is local, explicit and separate from installation or execution.

## Requirements

- Node.js 20.3+ and npm for the MCP server.
- Python 3.11+ and Bash on Linux, macOS or WSL for the plugin runtime.
- The application's compatible Python 3.11+ environment and installed test dependencies.
- uv for projects with uv.lock, Poetry for projects with poetry.lock; otherwise
  .venv/bin/python is preferred, with the runtime interpreter as fallback.
- Optional Python diagnostics: pyright-langserver on PATH.

Inspect the application's dependency constraints. Guidance covers FastAPI,
Pydantic, SQLAlchemy/SQLModel and Alembic without prescribing an application version.

## Install and use

Install from GitHub:

```bash
git clone https://github.com/alefiengo/fastapi-tools ~/dev/fastapi-tools
npm ci --prefix ~/dev/fastapi-tools/mcp-server
cd /path/to/your/fastapi-project
claude --plugin-dir ~/dev/fastapi-tools
```

For marketplace installation:

```bash
claude plugin marketplace add https://github.com/alefiengo/fastapi-tools
claude plugin install fastapi-tools@fastapi-tools-marketplace
```

From an existing local checkout:

```bash
# From this repository:
npm ci --prefix mcp-server
cd /path/to/your/fastapi-project
claude --plugin-dir /absolute/path/to/fastapi-tools
```

For a local marketplace installation:

```bash
claude plugin marketplace add /absolute/path/to/fastapi-tools
claude plugin install fastapi-tools@fastapi-tools-marketplace
```

Install server dependencies in the installed plugin's mcp-server directory.
Try: "Inspect this FastAPI project, run its tests and summarize failures."
Use `/fastapi-pr-review` for a focused review. app_port defaults to 8000 and
sets the default MCP HTTP inspection port. The plugin registers its server,
hooks and optional Python LSP through .mcp.json, hooks/hooks.json and .lsp.json.

## Codex and offline diagnosis

After installing MCP dependencies, launch Codex from the application workspace:

```bash
cd /path/to/your/fastapi-project
node /absolute/path/to/fastapi-tools/codex/run.mjs
```

Follow [Codex setup](docs/codex.md) to register this local plugin. The launcher
passes the bundle path per process; it does not install the plugin or change
user configuration. Shared skills and MCP work in both hosts. Claude agent
permissions, Stop hooks and Python LSP registration are not Codex guarantees;
Codex verification is explicit. See the [capability matrix](docs/capability-matrix.md).

```bash
python3 scripts/install-doctor.py --plugin-root "$PWD" --workspace /path/to/project
```

The doctor checks local prerequisites and registration without network access,
installations, builds or host configuration changes. Run it again after upgrades.

## Safe project initialization

Explicitly ask to create a new FastAPI project at an absolute, absent destination.
`initialize_project` requires `destination`, `projectName` and `explicitRequest: true`.
The existing parent must be outside an existing Python project or workspace.
Existing files, empty directories, dangling symlinks, symlink ancestors and nested
projects are refused. A private sibling staging directory is cleaned up; exclusive
OS publication prevents replacement of a destination created during generation.
No network, dependency installation, application imports, Git initialization or
server execution is performed. Review the generated README before explicitly
installing dependencies or running tests. The flag represents caller authorization;
it cannot independently prove what a user requested.

## Skills

- `fastapi-api-contracts`
- `fastapi-build-run`
- `fastapi-ci`
- `fastapi-codegen`
- `fastapi-contract-testing`
- `fastapi-database`
- `fastapi-docker`
- `fastapi-initializer`
- `fastapi-load-testing`
- `fastapi-modular-architecture`
- `fastapi-observability`
- `fastapi-performance`
- `fastapi-pr-review`
- `fastapi-pydantic-v1-to-v2-migration`
- `fastapi-security-hardening`
- `fastapi-testing`

Skills activate for FastAPI work through their descriptions. PR review is an
explicit command. The Pydantic migration skill checks installed versions before
changing models, settings or serialization.

## Agents

- `fastapi-api-designer`
- `fastapi-architect`
- `fastapi-code-reviewer`
- `fastapi-docker-reviewer`
- `fastapi-migration-reviewer`
- `fastapi-runtime-reviewer`
- `fastapi-test-writer`

Reviewers are read-only. Architect/API designer write design or contract documents;
test-writer writes tests and fixtures. The caller owns execution and provides
verification evidence. Review selects only roles relevant to the change.

## MCP tools

| Tool | Behavior |
|---|---|
| initialize_project | Generate a minimal project at an absent, explicitly requested destination |
| analyze_project | Nearest Python project, declared dependencies, environment and AST routes |
| run_build | compile, lint, typecheck, package, dependencies or verify/check |
| run_tests | pytest, optional relative testPath, fresh JUnit summaries |
| check_migrations | Alembic graph/errors/upgrade risks; explicit status runs alembic current |
| openapi_endpoints | Static, runtime /openapi.json or comparison; configurable documentPath |
| app_health | Selected health/readiness/liveness routes with configurable paths |

`compile` checks Python syntax without executing imports. `lint` uses Ruff;
`typecheck` uses mypy. `verify` runs syntax and Ruff, mypy or pytest when declared or configured
(including standalone configuration files). `package` uses build --no-isolation.
Missing dependencies and pytest's no-tests exit code are failures. Tools do not
install dependencies: uv uses --frozen --offline --no-sync. Synchronize the project
environment explicitly before running checks. Test selectors must remain inside
the project. Workspace/module aggregation is outside static discovery. Explicit lint/typecheck/test
requests require a declaration or configuration and fail if the tool is unavailable. A project
without pytest runs syntax and its configured checks; a configured pytest suite
with no collected tests retains pytest’s failure status.

Static analysis never imports application modules or Alembic env.py. Dependencies
are declarations, not a resolved graph; includes in requirements files and dynamic
setup metadata need manual inspection. Route analysis supports top-level app/router
constructors, imported routers, literal prefixes and decorators. Factories, mounts,
re-exports and computed/conditional registrations require runtime OpenAPI evidence.
Alembic lint inspects literal revisions, parents, dependencies, cycles and heads;
it does not establish which migrations have been applied.

FastAPI has no built-in health routes. Defaults are /health, /health/ready and
/health/live; supply `paths` matching the application. HTTP inspection accepts an
explicit baseUrl, fetches no external schema references and forwards no credentials.

## Hooks and verification

| Hook | Event | Behavior |
|---|---|---|
| guard-secrets | PreToolUse | Inspect proposed settings/config/.env credentials |
| guard-ddl | PreToolUse | Reject metadata.drop_all outside test/dev/local helpers |
| lint-migration | PostToolUse | Report Alembic revision errors and upgrade risks |
| post-edit-compile | PostToolUse | Record relevant edits for batched verification |
| verify-on-stop | Stop | Run or reuse equivalent successful full verification |

Build hooks activate only for projects with a FastAPI declaration or import.
Prose-only inputs are excluded from fingerprints. Checks serialize per project;
reuse requires matching task, test scope, environment and file contents. Failed,
cancelled or targeted test runs cannot satisfy the full gate. Force a rerun with
`run_build` force:true (CLI reuse:false). Generated state stays in private temporary
directories; pytest reports are written to the target project's .fastapi-tools/.

Guards cover common scalar settings and direct Python assignments/calls. They are
review aids, not complete secret scanners or an enforcement boundary. Malformed
hook input or missing Python produces a diagnostic. Keep independent CI checks.

## Development

```bash
node --check mcp-server/index.js
bash tests/run-all.sh
# Install example-only dependencies, then exercise a real FastAPI lifecycle:
python3 -m pip install -r tests/examples/requirements.txt
bash tests/examples/check.sh
```

Real tool integration uses separately prepared dependencies and exercises venv,
uv, Poetry, pytest, Ruff, mypy and Alembic. See [validation and limits](docs/audit-2026-10-31.md).
No measured skill or agent benefit is claimed; the [evidence inventory](docs/component-evidence.json)
and [offline evaluation methodology](docs/evaluation-methodology.md) distinguish
functional coverage from behavioral outcomes. GitHub Actions and automatic
Dependabot updates are disabled for this repository; application CI templates
remain available in `fastapi-ci`.

## Upgrade and release

Update the checkout to the exact release tag, run `npm ci --prefix mcp-server`,
run the doctor, and restart the host. Marketplace users must update their installed
bundle and install MCP dependencies there; updating a source checkout does not
refresh a host cache. For Codex, update the same registered local path and relaunch
through `codex/run.mjs`. The 0.3.0 release adds explicit initialization and Codex;
verification no longer requires undeclared pytest. See [CHANGELOG.md](CHANGELOG.md)
and the [release procedure](docs/releases.md).

See [CONTRIBUTING.md](CONTRIBUTING.md), [architecture](docs/architecture.md),
[behavioral evaluations](evals/README.md) and [SECURITY.md](SECURITY.md).
Licensed under the [MIT license](LICENSE).
Adapted from [Spring Boot Tools](https://github.com/alefiengo/spring-boot-tools)
for FastAPI and Python.
