---
type: llm
---

PASS uses analyze_project and shared run_build/run_tests discovery/execution,
preserves .venv/requirements and configured tools, investigates the startup
exception and distinguishes syntax/targeted tests from full verification and
runtime startup. Does not impose Ruff, mypy, uv or Poetry, install dependencies,
or start Uvicorn via a finite build check. Unexecuted actions stay proposals.
