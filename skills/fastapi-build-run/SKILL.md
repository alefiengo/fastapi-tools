---
name: fastapi-build-run
description: Build, run and troubleshoot FastAPI applications using their Python environment, uv/Poetry/pip configuration and Uvicorn. Use for startup, dependency or verification requests in a project that uses FastAPI; not for Python projects without FastAPI.
---

# Build Run for FastAPI

Start with `analyze_project`: inspect pyproject.toml/requirements, lockfile, Python constraint, import root and application entry point. Use the existing environment. Do not install or upgrade dependencies without task authorization.

Verify through the MCP tool first: `run_build` with `task: "verify"`. `run_build` supports compile (syntax), lint (Ruff), typecheck (mypy), package, dependencies and verify/check. `verify` runs syntax, then Ruff, mypy and the full pytest suite only when each is declared or configured in the project, in sequence, stopping on failure. A project that declares no pytest gets no test run from `verify`; report that gap. Missing tools fail visibly. Syntax checking does not prove importability or type correctness. Packaging uses `python -m build --no-isolation`; install the project's declared build backend separately if needed.

`run_tests` accepts a relative `testPath`, optionally `tests/test_orders.py::test_create`. Full verification reuse requires unchanged inputs and equivalent scope. A targeted test or compile cannot satisfy Stop verification. Force an intentional fresh `run_build` with `force: true`; `run_tests` always runs fresh. Do not clean or repeat successful checks without new evidence.

```bash
# Use the actual app module; this path is illustrative.
python -m uvicorn app.main:app --reload --port 8000
# For a uv project with its environment already synchronized:
uv run --frozen --offline --no-sync python -m uvicorn app.main:app --port 8000
# Without the MCP tool, run the same shared finite runtime directly.
# Claude Code substitutes the plugin root below when it loads this skill. In Codex,
# replace the placeholder with the absolute plugin directory (two levels above this SKILL.md).
python3 "${CLAUDE_PLUGIN_ROOT}/runtime/project_runtime.py" <<'JSON'
{"action":"run","projectRoot":"/path/to/project","task":"verify"}
JSON
```

Keep long-running Uvicorn processes outside the finite build tool. Use reload for development only. Inspect actual import errors, environment variables, port bindings and lifespan startup exceptions before changing architecture. The runtime selects uv when uv.lock exists, Poetry for poetry.lock, otherwise .venv/bin/python or its Python interpreter. uv checks disable implicit sync/network access; prepare the environment explicitly.
