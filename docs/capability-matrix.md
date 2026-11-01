# Capability matrix (0.3.0)

| Component | Claude Code | Local Codex adapter | Evidence or limit |
| --- | --- | --- | --- |
| Shared skills | `skills/` | Same `skills/` | CLI read 16. Registration does not establish model selection. |
| Specialist agents | `agents/` and host permissions | Not registered | Subagents and their restrictions are not automatically equivalent. |
| Hooks | Five hooks across three events | Explicitly disabled | CLI `plugin/read` returned zero hooks. No guards or automatic Stop. |
| MCP stdio | `.mcp.json` with Claude variables | `codex/mcp.json`, wrapper and launcher | Real protocol with CLI 0.166.0, without installation or model turns. |
| Discovery / AST | Shared Python runtime | Same runtime through MCP | No application imports; root from MCP cwd, including subdirectories. |
| Finite checks | Hooks/MCP/runtime | Explicit MCP/runtime | `run_build task:verify`; same locks and execution policies. |
| Pytest and JUnit | MCP/runtime | Same MCP/runtime | Tools must be installed in the application; the adapter does not install them. |
| Alembic | Static lint / explicit status | Same through MCP | Status executes configuration; lint does not query the database. |
| OpenAPI and health | Static / explicit HTTP | Same through MCP | FastAPI does not create health routes automatically; port from environment, default 8000. |
| Initialization | Shared tool/skill | Shared MCP catalog | `initialize_project`, with explicit authorization; runtime `action: initialize`. |
| Application port | `userConfig.app_port` | `FASTAPI_APP_PORT` | Claude's configuration schema is not translated. |
| LSP | `.lsp.json`, depending on host | No plugin integration | Claude LSP configuration is not imported. |
| Offline doctor | Checks Claude registration | Checks Codex registration and paths | Not an MCP tool; does not install or check authentication. |
| Doctor version checks | Manifests/package/lock/server | Requires agreement with 0.3.0 | Node/Python probes; standalone Codex metadata, without starting it. |
| Desktop / hosted web | Not established here | Not established here | Requires a local executor. Directory submission and UI flows were not verified. |

Deterministic tests cover the adapter and doctor; the optional protocol smoke
checks CLI package reading and temporarily registered MCP. These are not model
behavior evaluations. A separate install-smoke test verifies marketplace add,
plugin add and plugin list in a temporary CODEX_HOME; it does not validate startup
from the installed cache or desktop. The local protocol smoke confirmed 16 skills
and seven tools, counts enforced by release tests. Seven Node regressions exercise
the adapter and its limits. The real CLI protocol smoke passed without installation
or paid model calls.

Official documentation supports the
[compatibility overlay and explicit hook replacement](https://developers.openai.com/plugins/build/plugins).
The adapter disables existing Claude hooks even where other Codex surfaces offer
lifecycle hooks: their formats and guarantees are not assumed interchangeable.
See [Codex usage, tests and limits](codex.md).
