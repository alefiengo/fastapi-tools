# Architecture

The Node MCP server delegates project discovery, AST inventories and finite
checks to runtime/project_runtime.py, a Python 3.11+ standard-library runtime.
Bash hook launchers invoke hooks/scripts/hook-runtime.py, which shares that
runtime. Application code is never imported by static inspection.

## Discovery and commands

Walk upward to the nearest pyproject.toml, requirements.txt, setup.cfg or setup.py.
Read TOML and plain root requirements declarations. uv.lock selects uv, poetry.lock
selects Poetry, otherwise use .venv/bin/python or the runtime interpreter. Dynamic
setup metadata, requirements includes and workspace aggregation are outside the
static inventory. Hooks verify only projects declaring or importing FastAPI.

Tasks are allowlisted and invoked as argument arrays without a shell. verify
checks syntax, configured Ruff/mypy and pytest sequentially. uv does not sync or
access the network during checks. Project tool configuration, test plugins and
Alembic env.py are executable code when their associated task runs; trust the
repository. migration-status executes current, never upgrade/downgrade.

## Coordination

A private per-user/per-project temporary directory holds an advisory flock and
atomic state. All finite tasks acquire the same lock. File contents, modes,
environment and runtime implementation form the input fingerprint. Generated
caches, .venv, .fastapi-tools and output directories are excluded. External source
symlinks disable reuse; they never count as verified inputs. Limits bound file
count, bytes, subprocess output and total time including lock wait.

Only unchanged successful verify results are reusable at equivalent scope. Any
new attempt invalidates old success. Changing inputs during a check prevents
reuse and is exposed to callers. Post-edit hints are atomic and do not wait for
an active build. Stop independently checks final inputs, including edits through
other tools. The stop_hook_active flag prevents recursive Stop invocations.

pytest writes .fastapi-tools/pytest.xml. Snapshot contents and freshness are read
inside the project lock, so a queued test run cannot claim another run's reports.
JUnit parsing rejects entities/DTDs and oversized reports. Failed commands retain
stdout/stderr and stale report diagnostics. Cancellation/timeout kills descendants.

## Evidence limits

AST routes resolve ordinary imported routers and literal prefixes. Runtime OpenAPI
confirms registered routes; factories, mounts and dynamic registration need it.
Alembic AST lint checks literal revision graphs, missing parents, duplicates, cycles,
multiple heads and upgrade DDL risks. It neither imports env.py nor queries the
applied history. Explicit status and HTTP queries provide additional evidence.

HTTP fetches have deadlines and response limits, reject redirects and do not
forward credentials or resolve external references. Health routes are configurable;
FastAPI itself does not supply them. 401/403 and 404 are access/exposure diagnostics.
