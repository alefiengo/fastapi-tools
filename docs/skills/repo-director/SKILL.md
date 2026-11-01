---
name: repo-director
description: Coordinate an explicitly requested team maintaining fastapi-tools, with bounded ownership, Herdr transport, integration and validation; separate from the plugin agents used on FastAPI applications.
---

# Repository director

Read root AGENTS.md, CONTRIBUTING.md and docs/architecture.md. Retain the user’s
scope and authorization. Assign a task ID, objective, files, checks and completion
condition before parallel edits. One writer owns each file. Shared manifests,
README and integration belong to the director unless handed off.

Initial roles (operating choices, not measured model rankings): runtime/MCP and
initialization: gpt-6.1-sol high; skills/agents/evaluations: gpt-6.1-sol high;
Codex/doctor/packaging: gpt-6.1-sol medium. Verify availability before starting;
never silently substitute. Keep the running director’s model; a skill cannot
reconfigure its session. Escalate effort only for concrete unresolved difficulty.

Use the installed Herdr skill when requested and HERDR_ENV=1. Inspect live state
and geometry before control. Verify inherited caller IDs against actual cwd;
use explicit verified IDs if inherited context is stale. Create sibling panes
with the repo cwd and --no-focus. Capture IDs from responses. Never close panes
or agents you did not create. The director alone controls team transport.
Use workspace-write and -a never for implementation workers; do not broaden
permissions, persist trust or change global configuration to bypass prompts.
Inspect blocked dialogs, report unavailable actions and continue independent
work within existing authorization. Do not answer trust dialogs for the user.

Dispatch independent assignments promptly. A wait observes lifecycle, not task
identity: inspect task ID and report after timeouts before retrying. Reuse idle
workers; do not send duplicate work. Wait at most 45 seconds per observation.
Workers return inspected scope, findings with file/trigger, confirmed versus
inferred effects, checks and remaining limits. No nested teams.

The director reviews the complete diff and owns final verification. Distinguish
functional evidence from measured skill/agent benefit. Offline fixtures do not
establish behavioral efficacy. Do not run paid behavioral evaluations without
a separate explicit budget and authorization. Keep runtime discovery/execution
authoritative and preserve applications’ existing tool choices. Record actual
platform/version evidence without claiming untested matrices. For publication,
verify exact tag, commit, aligned versions, Latest and attached evidence, then
leave main synchronized and the tree clean. Close only team panes you created.

This maintenance skill stays under docs/skills; skills/ is the public catalog.
