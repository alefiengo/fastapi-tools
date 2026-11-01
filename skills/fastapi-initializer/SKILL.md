---
name: fastapi-initializer
description: Initialize a new FastAPI project in an absent destination using the initialize_project MCP capability. Use for explicit new-project scaffolding, not changes to an existing Python application.
---

# Initialize a FastAPI project

Inspect the loaded MCP tool schema before constructing a call. The coordinated
contract is `initialize_project({destination, projectName, explicitRequest: true})`,
delegating to the runtime's CLI action `initialize`. Confirm that the installed
version exposes that contract; do not assume a response format or extra options.
If the tool is unavailable or
cannot enforce the constraints below, report the gap instead of inventing an
API, using a shell scaffold, or bypassing its validation with file writes.

Resolve the proposed destination and inspect its ancestors before generation.
Use an absolute destination with an existing parent; reject traversal and
symlink ancestors rather than resolving them into a workaround.
Require an absent destination, including rejection of an existing empty directory
or dangling symlink. Protect Python project and workspace ancestors, including
pyproject.toml, requirements.txt, setup.cfg/setup.py and workspace configuration.
A nested new folder does not make an existing project an initialization target.
Do not remove markers, follow a link around a refusal, or overwrite existing work.
Let the authoritative runtime/MCP validation decide the final target boundary.

Establish `projectName` and `destination` from the user's request. Set
`explicitRequest: true` only when the user explicitly authorized generation at
that destination. Inspect the tool's supported template rather than inventing
Python-version or feature arguments. Preserve the user's
package manager and ORM choices; do not add SQLAlchemy, Alembic, uv, Poetry or a
database without a need. Present the concrete generation scope and obtain explicit
authorization for that destination if it is not already given in this session.
A request for advice, a preview or a proposed layout does not authorize writing.

Call the discovered tool only after those conditions hold. Generation is separate
from dependency installation, application execution, database changes, git actions
and publication. An authorization to scaffold does not authorize those actions.
Do not change host permissions, trust, or global configuration to make a call work.

Report the tool's actual result, created paths and unresolved prerequisites.
Scaffolded tests are unexecuted until run in a prepared environment. For a later
authorized verification, use the shared runtime through fastapi-build-run after
dependencies have been explicitly prepared; do not implement competing discovery.
