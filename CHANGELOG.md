# Changelog

## [0.4.0] - 2026-11-11

### Changed

- Move `package.json` and `package-lock.json` to the plugin root so Claude Code installs the locked MCP dependencies for marketplace installs; `mcp-server/package.json` only marks the directory as ESM. Update `fast-xml-parser` to 5.12.0 (GHSA-474x-hrwr-fgx4).
- MCP: HTTP inspection (`openapi_endpoints`, `app_health`) accepts only loopback hosts and a `baseUrl` of at most 2048 characters; builds are cancelled and their locks released on SIGINT, SIGTERM and SIGHUP; a symlinked plugin path starts correctly; the three inspection tools are annotated read-only; JUnit numeric character references are decoded.
- Runtime interpreter: MCP and hooks use `FASTAPI_TOOLS_PYTHON` or the first Python 3.11+ among `python3`, `python3.14` to `python3.11`, independent of the application environment. Hooks start through `hooks/scripts/launch.sh` and skip with a diagnostic when none qualifies. The MCP runtime and its version probe, the hooks, the check supervisor and the syntax check run with `python -I -S`, so `PYTHONPATH` and the `.pth` files of the application's environment no longer load into plugin code; build steps keep the caller's environment.
- Build state and locks live in `~/.cache/fastapi-tools` (a symlinked `~/.cache` is accepted when its target is private; override: `FASTAPI_TOOLS_STATE_HOME`, which Codex now forwards) instead of a directory that depends on `TMPDIR`. Only without a usable home does a `<TMPDIR or /tmp>/fastapi-tools-<uid>` fallback apply, reported as `stateDiagnostic` and in the Stop message.
- Discovery refuses project roots writable by other users and ancestor build files, lockfiles or environments that another user owns or others can write (group write is accepted only for the user's own private group). It also supports uv workspaces, `venv/` and an active `VIRTUAL_ENV` inside the root, mypy `files`/`packages`/`modules`, and parametrized pytest ids in `testPath`.
- Stop keeps edit hints per session, verifies the session root and the projects the session edited, always reruns and blocks after an edit by that session, and ignores a `cwd` outside the project. Without a hint it blocks only for changed inputs. A failure is remembered only when definitive and is tied to the identity of the environment (`uv sync` invalidates it). With `stop_hook_active` it still verifies but reports instead of blocking. Fingerprints now follow symlinks to ignored directories and exclude `*.db`, `*.sqlite*` and `*.log` by name.
- Guards report only findings an edit introduces and ask for confirmation on literals in `.env` files and tests; the test-path exemption is limited to `tests/` or `test/` at the root, configured pytest `testpaths`, `conftest.py`, `test_*.py` and `*_test.py`.
- Codex: `codex/mcp.json` forwards `FASTAPI_TOOLS_STATE_HOME`, `PYTHONPATH`, `VIRTUAL_ENV`, toolchain, uv, Poetry, XDG and proxy variables; `codex/run.mjs` no longer forwards SIGINT twice; `requires_local_executor` is removed (the loader never defined it).
- Skills: current guidance for JWT and password hashing (PyJWT, pwdlib), Pydantic v1 removal and gradual migration limits, native FastAPI telemetry, uv, SQLAlchemy 2.1 and pinned GitLab images, Docker with uv, and the `run_build` verify flow. Skill and agent descriptions are scoped to FastAPI contexts, and `fastapi-architect` and `fastapi-api-designer` return documents instead of writing files.
- Initializer scaffold declares `httpx2` in its test extra. Manifests declare `license`, `repository` and `homepage`.
- The offline doctor reads the root layout, compares versions with the Claude manifest instead of a literal, and warns about a leftover `mcp-server/node_modules`.

### Added

- Evaluation harness: MCP mock catalog and graders, negative cases, with-only agent graders, ablation fixes and a mock contract test.
- Regression suites for MCP host boundaries, skill code snippets and repository consistency (manifests, counts, versions, links and package layout).

### Compatibility

- Run `npm ci` at the repository root; `npm ci --prefix mcp-server` and `mcp-server/package-lock.json` no longer exist. Delete a stale `mcp-server/node_modules`.
- `baseUrl` values for non-loopback hosts are now refused.
- State directories from earlier versions under the system temporary directory are no longer used and can be deleted.
- Hooks require Python 3.11+ on PATH (or `FASTAPI_TOOLS_PYTHON`); previously any `python3` was used.
- Register Codex from a clean clone: Codex copies the whole directory, including `.git` and `node_modules`.
- Application environment variables other than those listed in `codex/mcp.json` do not reach the runtime under Codex.
- Projects whose directory is group-writable by a shared group are refused; a private per-user group (the Debian/Ubuntu default) is accepted.
- Changes to `*.db`, `*.sqlite*` and `*.log` files no longer invalidate verification reuse.

## [0.3.0] - 2026-11-01

- Add the Codex manifest and local adapter sharing skills, MCP and the Python runtime.
- Add offline installation diagnosis, protocol/installation smoke tests and host capability documentation.
- Publish the complete component evidence inventory, compatibility limits and reproducible validation report.

## [0.2.0] - 2026-11-01

- Explicit local project initialization with protected ancestors, private staging and exclusive publication.
- Add fastapi-initializer and initialize_project: 16 skills and seven MCP tools.
- Harden verification, cancellation, reports and bounded inspection; honor declared/configured Python tools.
- Add real venv/uv/Poetry fixtures, expanded FastAPI/Pydantic/SQLAlchemy/Alembic examples and an offline evaluation harness.

## [0.1.0] - 2026-11-01

- FastAPI toolkit for Claude Code with 15 skills, seven specialist agents, five hooks and six MCP tools.
- Shared Python project discovery, coordinated checks, static routes, Alembic inspection, pytest reports and configurable HTTP probes.
- Functional regression suites and executable FastAPI examples.

[0.1.0]: https://github.com/alefiengo/fastapi-tools/releases/tag/v0.1.0
[0.2.0]: https://github.com/alefiengo/fastapi-tools/releases/tag/v0.2.0
[0.3.0]: https://github.com/alefiengo/fastapi-tools/releases/tag/v0.3.0
[0.4.0]: https://github.com/alefiengo/fastapi-tools/releases/tag/v0.4.0
