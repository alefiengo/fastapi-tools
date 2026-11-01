# Architecture

The Node MCP server delegates project discovery, AST inventories and finite
checks to runtime/project_runtime.py, a Python 3.11+ standard-library runtime.
Bash hook launchers invoke hooks/scripts/hook-runtime.py, which shares that
runtime. Application code is never imported by static inspection.

## Discovery and commands

Walk upward to the nearest pyproject.toml, requirements.txt, setup.cfg or setup.py.
Read bounded TOML, setup.cfg, plain root requirements and tool configuration.
Includes and dynamic setup metadata are not resolved. uv.lock selects uv, poetry.lock
selects Poetry, otherwise use .venv/bin/python or the runtime interpreter. Ambiguous uv and Poetry
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

A private per-user/per-project temporary directory holds an advisory flock and
atomic state. All finite tasks acquire the same lock. File contents, modes,
environment and runtime implementation form the input fingerprint. Generated
caches, .venv, .fastapi-tools and output directories are excluded. External source
symlinks disable reuse; they never count as verified inputs. Stop blocks when the
final input fingerprint cannot be established. Discovery failures block Stop when
FastAPI evidence remains available; generic Python retains a diagnostic only. Limits bound file
count, bytes, subprocess output and total time including lock wait.

Only unchanged successful verify results are reusable at equivalent scope. Any
new attempt invalidates old success. Changing inputs during a check prevents
reuse and is exposed to callers. Post-edit hints are atomic and do not wait for
an active build. Stop independently checks final inputs, including edits through
other tools. The stop_hook_active flag prevents recursive Stop invocations.

pytest writes .fastapi-tools/pytest.xml. Snapshot contents and freshness are read
inside the project lock, so a queued test run cannot claim another run's reports.
JUnit parsing rejects entities/DTDs and oversized reports. Failed commands retain
stdout/stderr and stale report diagnostics. Cancellation/timeout kills descendants. Runtime CLI builds use a separate process
group with signal cleanup. Already-cancelled MCP requests do not spawn work;
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
forward credentials or resolve external references. Health routes are configurable;
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

## Host adapters and component choices

Codex uses its own manifest and MCP registration, sharing skills and the same
server/runtime. The per-process wrapper supplies the bundle root; the MCP launcher
selects its actual workspace cwd. It does not duplicate project discovery.
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
