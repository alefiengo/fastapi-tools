# Real Python ecosystem checks

Prepare the pinned requirements explicitly using CONTRIBUTING.md. Run check.sh
with ECOSYSTEM_PYTHON set to that environment’s Python. uv must be on PATH; Poetry
is installed in the prepared environment. --managers python uv poetry selects
which actual managers to exercise; missing tools fail rather than silently skip.

The fixtures create real temporary venvs without pip and expose the prepared
site-packages through PYTHONPATH. This isolates application files without
reinstalling dependencies. Manager fixtures have valid, empty dependency locks;
tools are preinstalled in the validation environment. This verifies actual
manager execution and environment selection, not remote dependency resolution,
installation, lock fidelity for full applications or workspace aggregation.

Initialization cases require a temporary base outside any protected project or
workspace; set TMPDIR to a suitable existing writable directory when needed.

Cases cover actual FastAPI requests, full verification/reuse, targeted JUnit
failure parsed through the real MCP server, Stop blocking, repair, Ruff/mypy/syntax failure, Alembic current against
SQLite without applying revisions, and bounded slow pytest. Deterministic suites
separately cover cancellation descendants, concurrent locks, queued report
freshness, environment changes and symlink rejection. No paid model calls.
