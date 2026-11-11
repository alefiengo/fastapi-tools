# Architecture

The Node MCP server delegates project discovery, AST inventories and finite
checks to runtime/project_runtime.py, a Python 3.11+ standard-library runtime.
Bash hook launchers delegate to hooks/scripts/launch.sh, which starts
hooks/scripts/hook-runtime.py with `python -I -S`; it shares that runtime. Application
code is never imported by static inspection.

The plugin runtime interpreter is independent of the application's environment. MCP
and hooks use `FASTAPI_TOOLS_PYTHON` when set; otherwise the first of `python3`,
`python3.14`, `python3.13`, `python3.12`, `python3.11` on PATH that reports 3.11 or
later. The MCP server starts the runtime and its version probe, the hooks, the
check supervisor and the syntax check with `-I -S`, so `PYTHON*` variables, the
script directory and site or `.pth` files of the active environment never load
into plugin code (the runtime uses only the standard library). Build steps keep
the caller's environment, `PYTHONPATH` included. If no interpreter qualifies, MCP
tools fail with an explicit message listing what was checked and hooks emit a
diagnostic and skip. The syntax check runs under the
application's interpreter, so runtime/source_inventory.py stays compatible with
Python 3.8 (`-I` exists since 3.4). The MCP package.json and lockfile sit at the plugin root, where Claude
Code looks for dependencies to install; mcp-server/package.json only marks the
server directory as ESM. `.mcp.json` sets no `cwd`: the project root reaches the
server through `PROJECT_ROOT`.

## Discovery and commands

Walk upward to the nearest pyproject.toml, requirements.txt, setup.cfg or setup.py.
Read bounded TOML, setup.cfg, plain root requirements and tool configuration.
Includes and dynamic setup metadata are not resolved. uv.lock selects uv, poetry.lock
selects Poetry, otherwise use .venv/bin/python, venv/bin/python, an active
`VIRTUAL_ENV` inside the project root or the runtime interpreter. An enclosing uv
workspace owns the lockfile and environment of its members; a missing uv environment
is an error rather than an implicit creation. mypy honors configured `files`,
`packages` and `modules`. Discovery refuses a project root writable by other users
and a build file, lockfile or environment in an ancestor owned by another user or
writable by others; group write counts unless the group is the user's own private
group (primary group named like the user, with no other members). Ambiguous uv and Poetry
lockfiles are refused; Poetry checks disable automatic environment creation. Dynamic
setup metadata, requirements includes and workspace aggregation are outside the
static inventory. Hooks verify only projects declaring or importing FastAPI.

Tasks are allowlisted and invoked as argument arrays without a shell. verify
checks syntax and declared/configured Ruff, mypy and pytest sequentially. Explicit
lint/typecheck/test requests require that tool to be declared or configured. No undeclared test framework is imposed. uv does not sync or
access the network during checks. Project tool configuration, test plugins and
Alembic env.py are executable code when their associated task runs; trust the
repository. migration-status executes current, never upgrade/downgrade.

## Coordination

A private (0700) per-user/per-project directory holds an advisory flock and atomic
state: `<passwd home>/.cache/fastapi-tools/build-<sha256 of the resolved project
root>`. `~/.cache` may be a symlink if its resolved target belongs to the user and
only the user can write it. `FASTAPI_TOOLS_STATE_HOME` (absolute, private 0700) is an
explicit override, forwarded to the MCP server by `codex/mcp.json`. Only without a
usable home directory or `~/.cache` does the runtime fall back to
`<TMPDIR or /tmp>/fastapi-tools-<uid>`; processes with a different `TMPDIR` then do
not share locks or results, so the runtime reports `stateDiagnostic` in every result
and the Stop hook adds it to its message. All finite tasks acquire the same lock. File contents, modes,
environment variables, the identity of the selected environment (`pyvenv.cfg` plus
installed distribution and `.pth` names) and runtime implementation (including
runtime/source_inventory.py) form the input fingerprint. Generated caches,
directories containing `pyvenv.cfg`, .venv, .claude, .fastapi-tools, output
directories and `[tool.fastapi-tools] fingerprint-exclude` patterns are excluded, as
are files named `*.db`, `*.sqlite*`, `*.log`, `.coverage*` and `coverage.xml` anywhere
in the project (a change to a versioned fixture database does not invalidate
reuse). Symlinks inside the project are inputs; a link to an ignored directory
hashes the target's contents under the link's name. External or dangling links, and
symlinks nested in such a target, prevent a successful result and reuse. Edit hints
are stored per session (`session_id`). Stop verifies the session root (the hook
`cwd` counts only inside the project's worktrees) and the projects this session
edited. With a hint from this session it always reruns the verification and blocks
on failure; without one it blocks only when the inputs changed since the last
attempt, and a failure on unchanged inputs and environment is reported instead of
rerun. A failure is remembered only when definitive (inputs unchanged during the
run, no timeout, no output limit). A final fingerprint that cannot be established
makes verification incomplete and follows the same rule. Discovery failures block Stop
when FastAPI evidence remains available; generic Python retains a diagnostic only. Limits bound file
count, bytes, subprocess output and total time including lock wait; the Stop budget
is 540 seconds.

Only unchanged successful verify results are reusable at equivalent scope. Any
new attempt invalidates old success. Changing inputs during a check prevents
reuse and is exposed to callers. Post-edit hints are atomic (their own file and lock, never the build lock)
and do not wait for an active build. Stop independently checks final inputs, including edits through
other tools. With `stop_hook_active` (Claude continuing after a block) Stop still
verifies but reports with a `systemMessage` instead of blocking again, so it cannot
loop and does not skip verification.

pytest writes .fastapi-tools/pytest.xml. Snapshot contents and freshness are read
inside the project lock, so a queued test run cannot claim another run's reports.
JUnit parsing rejects DTD/entity declarations and oversized reports and decodes
only the five XML entities and numeric character references. Failed commands retain
stdout/stderr and stale report diagnostics. Cancellation/timeout kills descendants. Runtime CLI builds use a separate process
group with signal cleanup. On SIGINT, SIGTERM or SIGHUP the MCP server signals the
runtime of every active build, which kills its own process group and releases the
lock, then exits with 128 plus the signal number. Already-cancelled MCP requests do not spawn work;
schema-less tool handlers preserve the SDK context. Report capture failures retain
command diagnostics and become structured errors. Static reads reject symlinks,
FIFOs and oversized files; traversal, serialized output and hook input are bounded.

## Evidence limits

AST routes resolve ordinary imported routers and literal prefixes. Runtime OpenAPI
confirms registered routes; factories, mounts and dynamic registration need it.
Alembic AST lint checks literal revision graphs, missing parents, duplicates, cycles,
multiple heads and upgrade DDL risks. It neither imports env.py nor queries the
applied history. Explicit status and HTTP queries provide additional evidence.

HTTP fetches have deadlines and response limits, reject redirects and do not
forward credentials or resolve external references. `baseUrl` (at most 2048
characters) must name a loopback host (`localhost`, 127.0.0.0/8, `[::1]`; numeric
forms are normalized by the URL parser first); anything else is refused before a
request, so the tools cannot reach LAN or metadata services. Health routes are configurable;
FastAPI itself does not supply them. 401/403 and 404 are access/exposure diagnostics.

## Explicit initialization

`initialize_project` delegates to runtime CLI `action: initialize`, then to
runtime/project_initializer.py. It requires explicitRequest=true, a validated
projectName and an absolute absent destination whose parent already exists.
Generation never depends on discovering an existing project. All ancestors are
walked through directory descriptors without following symlinks and checked for
Python/project/workspace markers, including dangling metadata symlinks.

The local template writes private files into a randomly named sibling staging
directory. Before publication, it rechecks protected ancestors and parent identity.
Linux renameat2 RENAME_NOREPLACE / macOS renameatx_np RENAME_EXCL atomically refuse
concurrent destinations, including empty directories. Unsupported primitives fail
closed. Failure/signal cleanup uses the anchored parent descriptor. There are no
network calls, installers, application imports, Git commands or server starts.
Staging is the only temporary write outside the requested destination. A process
with adversarial parent-directory write access remains outside the trust boundary.
A filesystem without exclusive rename (for example WSL `/mnt/c`) is refused with an
explicit message. The scaffold's `test` extra declares pytest and httpx2:
Starlette's `TestClient` deprecates httpx in favor of httpx2.

## Host adapters and component choices

Codex uses its own manifest and MCP registration, sharing skills and the same
server/runtime. The per-process wrapper supplies the bundle root; the MCP launcher
selects its actual workspace cwd. It does not duplicate project discovery. Codex
passes only a fixed environment plus the `env_vars` names in codex/mcp.json (see
codex.md). That list includes `VIRTUAL_ENV` and `PYTHONPATH` (build steps need
them; the runtime itself ignores them through `-I -S`), but application settings
such as `DATABASE_URL` do not reach the runtime there.
Claude agents, hooks, LSP and userConfig are not translated. Explicit empty Codex
hooks suppress accidental Claude hook discovery. See codex.md and capability-matrix.md.
The offline doctor resolves dependencies and checks registration without starting
hosts/MCP, importing application code, installing packages or contacting services.

The inexpensive post-edit hook remains compatible: it records a pending hint,
while Stop independently fingerprints final inputs. The hint is advisory and is
never proof of success. The redundant in-process MCP active-test set was removed: every request now
queues through the authoritative runtime lock, including other servers and hooks. Optional LSP remains a host capability. YAML is only a development
dependency for catalog/fixture validation; it is not required by MCP execution.
No separate discovery scripts or build runners were added to host adapters.

Maintenance instructions and the repository-director skill live under AGENTS.md
and docs/skills, outside the distributed skill catalog. Behavioral evaluation
preparation/comparison is offline and distinct from deterministic tests and real
Python ecosystem fixtures; see evaluation-methodology.md for evidence limits.

## Official design references

Consulted 2026-10-31: [FastAPI environments](https://fastapi.tiangolo.com/virtual-environments/),
[testing](https://fastapi.tiangolo.com/tutorial/testing/),
[routers](https://fastapi.tiangolo.com/tutorial/bigger-applications/),
[uv CLI](https://docs.astral.sh/uv/reference/cli/),
[Poetry CLI](https://python-poetry.org/docs/cli/),
[pytest output](https://docs.pytest.org/en/stable/how-to/output.html),
[Ruff integrations](https://docs.astral.sh/ruff/integrations/),
[mypy execution](https://mypy.readthedocs.io/en/stable/running_mypy.html),
[Alembic tutorial](https://alembic.sqlalchemy.org/en/latest/tutorial.html) and
[OpenAI plugin packaging](https://developers.openai.com/plugins/build/plugins).
Implementation decisions also use installed SDK/CLI code and executable regressions;
documentation alone does not establish compatibility of an untested platform.
