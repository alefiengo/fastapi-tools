# FastAPI Tools for Claude Code and Codex

[![Release](https://img.shields.io/github/v/release/alefiengo/fastapi-tools)](https://github.com/alefiengo/fastapi-tools/releases/latest)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

A local plugin for developing and reviewing FastAPI applications: 16 shared skills
and seven MCP tools. Claude Code also registers seven specialist agents and five
hooks. Both hosts share Python discovery, process locks and verification records.
Project initialization is local, explicit and separate from installation or execution.

## Requirements

- Node.js 20.3+ and npm for the MCP server.
- Python 3.11+, Bash and POSIX facilities for the plugin runtime; native Windows is unsupported.
  The runtime interpreter is independent of the application's environment. MCP and
  hooks use `FASTAPI_TOOLS_PYTHON` when set; otherwise the first of `python3`,
  `python3.14`, `python3.13`, `python3.12`, `python3.11` on PATH that reports 3.11
  or later. If none qualifies, the tools fail with an explicit message and the hooks
  skip with a diagnostic.
- The application's own Python environment and its declared/configured check tools.
- uv for projects with uv.lock, Poetry for projects with poetry.lock; otherwise
  `.venv/bin/python`, then `venv/bin/python`, then an active `VIRTUAL_ENV` inside
  the project root, with the runtime interpreter as fallback.
- Optional Python diagnostics in Claude Code: install `pyright-langserver` with
  `npm install -g pyright`, `pipx install pyright` or `pip install pyright`, and make
  sure it is on the PATH of the shell that starts `claude`. This plugin registers the
  same server as Anthropic's `pyright-lsp` plugin; do not enable both at once. Their
  combined behavior (for example duplicated diagnostics) has not been verified.

Inspect the application's dependency constraints. Guidance covers FastAPI,
Pydantic, SQLAlchemy/SQLModel and Alembic without prescribing an application version.
The 0.4.0 release validation used Linux on WSL2 with Node 24.21.0 and Python 3.12.15;
the deterministic suites also ran with Python 3.11.17 and the MCP server started on
Node 20.3.0. macOS is an implementation target without an executed validation. The
prerequisite ranges above are not evidence that every Node/Python combination was tested.

## Install and use

Install from GitHub:

```bash
git clone --branch v0.4.0 https://github.com/alefiengo/fastapi-tools ~/dev/fastapi-tools
npm ci --omit=dev --prefix ~/dev/fastapi-tools
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
# From this repository (the lockfile is at the repository root):
npm ci
cd /path/to/your/fastapi-project
claude --plugin-dir /absolute/path/to/fastapi-tools
```

For a local marketplace installation:

```bash
claude plugin marketplace add /absolute/path/to/fastapi-tools
claude plugin install fastapi-tools@fastapi-tools-marketplace
```

Marketplace installs from a git or GitHub source install the locked server
dependencies automatically (npm must be on PATH). `--plugin-dir` and local-path
marketplaces load the checkout in place: run `npm ci` in its root first. The
package.json and package-lock.json live at the plugin root so that Claude Code can
find them; mcp-server/package.json only marks the server directory as ESM.
Try: "Inspect this FastAPI project, run its tests and summarize failures."
Use `/fastapi-tools:fastapi-pr-review` in Claude Code for a focused review.
Plugin skills use the [plugin namespace](https://code.claude.com/docs/en/plugins).
app_port defaults to 8000 and sets the default MCP HTTP inspection port.
The plugin registers its server,
hooks and optional Python LSP through .mcp.json, hooks/hooks.json and .lsp.json.
The server receives the project root in `PROJECT_ROOT` (from `CLAUDE_PROJECT_DIR`).

## Codex and offline diagnosis

Register the local plugin following [Codex setup](docs/codex.md), then install
MCP dependencies and launch Codex from the application workspace:

```bash
cd /path/to/your/fastapi-project
node /absolute/path/to/fastapi-tools/codex/run.mjs
```

The launcher passes the bundle path per process; it does not install the plugin
or change user configuration. Codex copies the whole registered directory into its
cache, so register a clean clone rather than a working tree with `.git`,
`node_modules` and caches. Shared skills and MCP work in both hosts. Claude agent
permissions, Stop hooks and Python LSP registration are not Codex guarantees;
Codex verification is explicit. See the [capability matrix](docs/capability-matrix.md).

```bash
python3 /absolute/path/to/fastapi-tools/scripts/install-doctor.py \
  --workspace /path/to/project --project /path/to/project
```

The doctor checks local prerequisites and registration without network access,
installations, builds or host configuration changes. Run it again after upgrades.

## Safe project initialization

Explicitly ask to create a new FastAPI project at an absolute, absent destination.
`initialize_project` requires `destination`, `projectName` and `explicitRequest: true`.
The existing parent must be outside an existing Python project or workspace.
Existing files, empty directories, dangling symlinks, symlink ancestors and nested
projects are refused. The destination must be on a local Linux/macOS filesystem
that supports exclusive directory rename; for example `/mnt/c` under WSL is refused. Private sibling staging is removed on handled failures and
cancellation; abrupt termination can leave a private staging directory. Exclusive
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

Skill descriptions guide host/model selection; activation and response quality
have not been measured. PR review is explicitly invoked. The Pydantic migration
skill instructs the caller to inspect installed versions before changing models,
settings or serialization; the skill itself is not an executable version check.

## Agents

- `fastapi-api-designer`
- `fastapi-architect`
- `fastapi-code-reviewer`
- `fastapi-docker-reviewer`
- `fastapi-migration-reviewer`
- `fastapi-runtime-reviewer`
- `fastapi-test-writer`

Claude reviewer, architect and API designer definitions allow Read, Glob and Grep
only; the designers return their documents in the response. The test-writer is the
only agent with Write and Edit, and its tests-and-fixtures scope is an instruction,
not filesystem isolation. The caller owns execution and provides verification
evidence. Review selects only roles relevant to the change.

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

`compile` checks Python syntax without importing application modules. `lint` uses Ruff;
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
explicit baseUrl (at most 2048 characters) only for loopback hosts: `localhost`,
127.0.0.0/8 and `[::1]`; other hosts are refused before any request. It fetches no
external schema references and forwards no credentials. `analyze_project`,
`openapi_endpoints` and `app_health` are annotated read-only.

The runtime may run as a different Python than the application. `FASTAPI_TOOLS_PYTHON`
or the PATH search described under Requirements selects it, and the runtime starts
with `python -I -S` (no `PYTHON*` variables, script directory, site or `.pth` files),
as do the hooks, the check supervisor and the syntax check that runs under the
application's own interpreter. The checks themselves (pytest, Ruff, mypy) keep the
caller's environment, `PYTHONPATH` included. `testPath` accepts parametrized pytest ids such as
`tests/test_api.py::test_item[param-id]` in the last path component only.

## Hooks and verification

| Hook | Event | Behavior |
|---|---|---|
| guard-secrets | PreToolUse | Inspect proposed settings/config/.env credentials |
| guard-ddl | PreToolUse | Reject metadata.drop_all outside test/dev/local helpers |
| lint-migration | PostToolUse | Report Alembic revision errors and upgrade risks |
| post-edit-compile | PostToolUse | Record relevant edits for batched verification |
| verify-on-stop | Stop | Run or reuse equivalent successful full verification |

Build hooks activate only for projects with a FastAPI declaration or import.
Edit hints are recorded per session (`session_id`), so one session never consumes
another's. Stop verifies the session's project root (the session `cwd` only inside
one of the project's worktrees; a `cwd` outside the project does not widen the scope)
and every project this session edited. With an edit hint from this session it always
reruns the verification and blocks with the failure; a remembered failure cannot
turn that gate into a notice. Without a hint it blocks only when the inputs changed
since the last attempt, and a failure on unchanged inputs and environment is
reported with a `systemMessage` instead of rerun. A failure is remembered only when
it is definitive: inputs unchanged during the run, no timeout and no output limit.
When Claude continues after a block (`stop_hook_active`), Stop still verifies but
reports without blocking again. The Stop budget is 540 seconds. After metadata errors, Stop blocks when static FastAPI
import evidence remains; otherwise it reports a diagnostic without establishing
framework identity.

Fingerprints exclude directories containing `pyvenv.cfg`, `.claude` and the
patterns in `[tool.fastapi-tools] fingerprint-exclude`. Files named `*.db`,
`*.sqlite*`, `*.log`, `.coverage*` or `coverage.xml` are excluded by name anywhere in
the project (they are what tests write), so a change to a versioned fixture database
does not invalidate reuse. Files ending in .md, .rst or .adoc outside src are
excluded; those under src remain build inputs. Symlinks that stay inside the project
are inputs, including a link to a directory that is itself ignored (its contents are
hashed under the link's name); external, dangling or nested links in such a target
prevent a successful verification result. Checks serialize per project; reuse
requires matching task, test scope, file contents and the identity of the selected
environment (`pyvenv.cfg` and the installed distribution and `.pth` names, so a
`uv sync` invalidates it). Failed, cancelled or targeted test runs cannot
satisfy the full gate. Force a rerun with `run_build` force:true (CLI reuse:false).
Locks and state live in `<passwd home>/.cache/fastapi-tools/build-<sha256 of the
resolved project root>` (mode 0700). `~/.cache` may be a symlink when its resolved
target belongs to the user and only the user can write it. `FASTAPI_TOOLS_STATE_HOME`
(an absolute, private 0700 directory) overrides the location and is forwarded by
`codex/mcp.json`, so both hosts can share it. Only when no usable home directory or
`~/.cache` exists does the runtime fall back to `<TMPDIR or /tmp>/fastapi-tools-<uid>`;
it then reports `stateDiagnostic` in every runtime result and in the Stop hook
message, because processes with a different `TMPDIR` do not share that fallback's
locks or results. Pytest reports are written to the target project's
.fastapi-tools/.

Discovery refuses a project root writable by other users and a build file,
lockfile or environment in an ancestor directory owned by another user or writable
by others. Group write counts as writable unless the group is the user's own
private group (primary group named like the user, with no other members). uv workspace members use the workspace lockfile and environment. mypy
honors configured `files`, `packages` and `modules`.

Guards inspect only findings introduced by the proposed edit. A literal credential
in a `.env` file or a test path asks for confirmation; elsewhere it is denied.
`metadata.drop_all()` is denied outside test/dev/local helpers. A test path is
`tests/` or `test/` at the project root, a configured pytest `testpaths` entry
(pyproject, pytest.ini, tox.ini or setup.cfg), `conftest.py`, `test_*.py` or
`*_test.py`; a `fixtures/`, `testing/` or `tests/` directory elsewhere in the
application is production code. Guards cover common
scalar settings and direct Python assignments/calls. They are review aids, not
complete secret scanners or an enforcement boundary. Malformed hook input or
missing Python produces a diagnostic. Keep independent checks in the application's CI.

## Development

```bash
npm ci
node --check mcp-server/index.js
# Fixtures that create projects use TMPDIR (default /var/tmp); choose an existing
# writable base outside any Python project or workspace. Runtime state does not use it.
export TMPDIR=/var/tmp
bash tests/run-all.sh
# Prepare example dependencies in a local environment, then exercise FastAPI:
python3 -m venv .fastapi-tools/example-env
.fastapi-tools/example-env/bin/python -m pip install -r tests/examples/requirements.txt
EXAMPLES_PYTHON="$PWD/.fastapi-tools/example-env/bin/python" bash tests/examples/check.sh
```

Real tool integration uses separately prepared dependencies and exercises venv,
uv, Poetry, pytest, Ruff, mypy and Alembic. See [validation and limits](docs/validation.md).
No measured skill or agent benefit is claimed; the [evidence inventory](docs/component-evidence.json)
and [offline evaluation methodology](docs/evaluation-methodology.md) distinguish
functional coverage from behavioral outcomes. GitHub Actions and automatic
Dependabot updates are disabled for this repository; application CI templates
remain available in `fastapi-ci`.

## Upgrade and release

Update the checkout to the exact release tag, run `npm ci --omit=dev` in its root,
run the doctor, and restart the host. Marketplace users run `claude plugin update`;
Claude Code installs the locked dependencies into the new cached version. Updating a
source checkout does not refresh a host cache. A leftover `mcp-server/node_modules`
from an older checkout shadows the root dependencies: the doctor warns about it; remove it. For Codex, update the same registered local path and relaunch
through `codex/run.mjs`. See [CHANGELOG.md](CHANGELOG.md) for features and compatibility changes
and the [release procedure](docs/releases.md).

See [CONTRIBUTING.md](CONTRIBUTING.md), [architecture](docs/architecture.md),
[behavioral evaluations](evals/README.md) and [SECURITY.md](SECURITY.md).
Licensed under the [MIT license](LICENSE).
