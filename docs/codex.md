# Codex: local adapter and offline diagnostics

The plugin provides `.codex-plugin/plugin.json`, reuses `skills/` and references
`codex/mcp.json`. OpenAI documents this compatibility format. The manifest carries no
`requires_local_executor` key: it is not defined by the Codex loader or by OpenAI's
guide, so it never had an effect. The root `.mcp.json`
belongs to Claude Code: its project variables and `user_config` must not be copied
to Codex.

## Local use

Linux/macOS, Node >=20.3, Python >=3.11 and the locked dependencies (package.json and
package-lock.json at the plugin root) must be prepared beforehand. The adapter does not install dependencies.
Application checks need their own Python environment and tools; only the runtime
selects uv, Poetry or `.venv`.

Prepare the locked server dependencies before installing the plugin:

```bash
npm ci --omit=dev --prefix /absolute/path/fastapi-tools
```

Codex installs by copying the registered directory into its cache, including `.git`,
`node_modules` and `__pycache__` when present (measured with codex-cli 0.167.0:
21 MB from a working tree). Register a clean clone of the release tag instead of a
development checkout.

Create a local marketplace outside the checkout and application. The following
commands are an installation recipe. The doctor does not run them; the optional
install-smoke test verifies them only in a temporary CODEX_HOME. Replace the
example paths and keep the checkout available:

```bash
mkdir -p /absolute/path/fastapi-local/.agents/plugins
ln -s /absolute/path/fastapi-tools /absolute/path/fastapi-local/fastapi-tools
```

Save this catalog as
`/absolute/path/fastapi-local/.agents/plugins/marketplace.json`:

```json
{
  "name": "fastapi-local",
  "interface": { "displayName": "FastAPI local" },
  "plugins": [
    {
      "name": "fastapi-tools",
      "source": { "source": "local", "path": "./fastapi-tools" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_USE" }
    }
  ]
}
```

Register the marketplace and install the plugin. These commands write to the
local Codex registry/cache and require an explicit user action:

```bash
codex plugin marketplace add /absolute/path/fastapi-local
codex plugin add fastapi-tools@fastapi-local
```

Codex CLI 0.167.1 confirmed this recipe and local installation in a temporary
CODEX_HOME on 2026-11-11 (0.166.0 did so when the adapter was first released): marketplace add,
plugin add and plugin list reported the plugin version enabled. The separate
protocol test registers MCP temporarily; it does not establish startup from the
installed cache. Then start through the wrapper from the same checkout version:

```bash
node /absolute/path/fastapi-tools/codex/run.mjs -C /absolute/path/application
```

The wrapper resolves its own location and passes `FASTAPI_TOOLS_PLUGIN_ROOT` only
to the child process. It preserves arguments, cwd and exit status without writing
configuration. MCP requires this absolute path and fails visibly if it is missing.
`codex/mcp.json` forwards that variable and `FASTAPI_APP_PORT` through `env_vars`
(plus the toolchain variables listed below); it contains no Claude interpolation and
does not set `cwd`. The default port is 8000. For example:

```bash
FASTAPI_APP_PORT=8181 node /path/fastapi-tools/codex/run.mjs -C /path/application
```

`codex/launch.mjs` replaces any inherited `PROJECT_ROOT` with the MCP process's
actual cwd and loads the shared server. It neither discovers projects nor builds
alternative commands. Use `analyze_project` to check the selected root. Changing
a shell tool's directory does not change an already running MCP process's cwd:
start a new session for another application. Keep the installed plugin and wrapper
versions aligned; the wrapper loads MCP from its own checkout.

The explicit path handoff avoids depending on `${PLUGIN_ROOT}` expansion in the
compatibility loader. This repository's tests validate the wrapper and its
configuration with Codex 0.167.1; they do not test automatic expansion of that
variable. Compatibility is not established for bare `codex` startup without the
variable or desktop startup without this environment.

## Environment forwarded to MCP

Codex starts MCP servers with only HOME, LOGNAME, PATH, SHELL, USER, LANG, LC_ALL,
TERM, TMPDIR, TZ, `__CF_USER_TEXT_ENCODING` (plus non-empty CA bundle variables) and the names listed in
`env_vars` (codex-rs/rmcp-client/src/utils.rs, rust-v0.167.0). `codex/mcp.json`
additionally forwards the plugin root and port, `FASTAPI_TOOLS_PYTHON`,
`FASTAPI_TOOLS_STATE_HOME`,
`VIRTUAL_ENV`, `PYTHONPATH`, uv (`UV_PROJECT_ENVIRONMENT`, `UV_CACHE_DIR`,
`UV_PYTHON`, `UV_PYTHON_INSTALL_DIR`), Poetry (`POETRY_HOME`, `POETRY_DATA_DIR`,
`POETRY_CONFIG_DIR`, `POETRY_CACHE_DIR`, `POETRY_VIRTUALENVS_PATH`,
`POETRY_VIRTUALENVS_IN_PROJECT`), XDG directories and HTTP(S)/NO proxy variables.
`FASTAPI_TOOLS_STATE_HOME` is also forwarded, so a location chosen for Claude Code is
shared. `VIRTUAL_ENV` and `PYTHONPATH` reach build steps (the plugin runtime itself
starts with `-I -S` and ignores them). Application variables such as `DATABASE_URL`
or pydantic-settings values are not forwarded, so tests and `alembic current` can behave differently than in Claude
Code, which inherits the full environment. Keep such settings in the application's
own configuration files (for example `.env`) when using Codex.

The Codex 0.167.0 manifest loader (codex-rs/core-plugins/src/manifest.rs) reads
`name`, `version`, `description`, `keywords`, `skills`, `mcpServers`, `apps`, `hooks`,
`interface` (including `developerName` and `websiteURL`) and `extensions`; other keys
are ignored without error. The `author`, `license`, `repository` and `homepage` keys
in `.codex-plugin/plugin.json` follow OpenAI's portable manifest example and
identify the plugin to people and tools; the loader does not use them.

## Offline doctor

The doctor requires Python 3.11+ and uses the standard library. Run it with a
trusted checkout and trusted Node/Python executables:

```bash
python3 /path/fastapi-tools/scripts/install-doctor.py --workspace /path/application
python3 /path/fastapi-tools/scripts/install-doctor.py --json \
  --workspace /path/application/app --project /path/application
```

`--plugin-root` defaults to the script's checkout; `--workspace` defaults to cwd.
`--node` and `--python` select executables, without shell arguments. The workspace
must exist outside the bundle. `--project` adds two static `action: discover`
runtime queries and compares canonical roots; a workspace nested within the same
project is supported. It does not import the application or run `setup.py`, tests,
migrations, package managers or project tools.

It checks:

- Linux/macOS, Node/Python versions and paths, and Codex availability on PATH.
- Manifest JSON and internal paths, Claude/Codex registration, explicit hook
  suppression and reuse of skills, MCP and runtime.
- The exact supported loader, inherited cwd, forwarded variables and wrapper path.
- Agreement of the plugin, marketplace, Codex manifest, package, lock and server
  versions with `.claude-plugin/plugin.json`, and of the dependency declarations
  between package and lockfile, both at the plugin root. A leftover
  `mcp-server/node_modules` is reported as a warning because it shadows them.
- Local ESM export resolution and file existence, including
  `@modelcontextprotocol/server/stdio`, without importing dependencies.

It does not run Codex: even `codex --version` attempted to create local aliases in
this installation. When the standalone package's `codex-package.json` is next to
the resolved binary, the doctor validates its entrypoint and reads the version as
metadata. Other installation formats may leave `version: null`; the report shows
`versionProbe: skipped`. This does not establish host compatibility or authentication.

The doctor uses no network, writes no files, installs no packages, changes no
configuration and starts no MCP server or host. Its only executions are bounded
Node/Python probes and optional static discovery, using isolated Python without
site initialization. Each probe has a five-second deadline and a 64 KiB output
limit. Inherited preload, coverage, cache and history variables are removed to
avoid incidental loading or writes. Dependency resolution does not establish
integrity, installed-version compatibility or successful MCP startup. The doctor
also does not inspect cached installed skills or another process's cwd.

JSON output contains `schemaVersion: 1`, `ok`, `exitCode`, `pluginRoot`, `workspace`
and ordered `checks` with `id`, `status`, `message` and check-specific evidence.
Statuses are `ok`, `warning`, `error`, `skipped`. Messages are not an API contract.
Exit codes: 0 for no errors (warnings/skips allowed), 1 for failed diagnostics,
2 for invalid arguments (argparse usage on stderr, including with `--json`). A
missing or outdated Python interpreter must be prepared before the doctor can start.

## Differences and limits

Shared skills retain Claude-oriented instructions where applicable; declaring
their directory does not translate host tools or subagents, or guarantee model
selection. `agents/` is not registered as Codex agents. Reading their guidance
manually is not equivalent to running independent reviewers.

The manifest sets `hooks: {"hooks": {}}`, suppressing default discovery of
`hooks/hooks.json`. This adapter provides no guards, post-edit compilation or
automatic Stop verification. Explicitly request `run_build` with `task: verify`
and inspect the result. Locks, limits, cancellation and verification reuse remain
the runtime's responsibility. `.lsp.json`, Claude agent models/permissions and
`userConfig` are not translated either.

The seven tools are `analyze_project`, `run_build`, `run_tests`, `check_migrations`,
`openapi_endpoints`, `app_health` and `initialize_project`. The adapter exposes the
server catalog without maintaining its own list. Initialization uses `destination`,
`projectName`, `explicitRequest: true`; the runtime handles `action: initialize`.
Do not infer generation authorization from missing files. The doctor does not
invoke initialization. The shared runtime owns its concrete policies.

Static analysis imports no code and does not confirm dynamic routes. Explicit
checks can execute pytest configuration, tools and Alembic; the application must
be trusted. HTTP/status modes have the effects and limits described in the
architecture. Hosted web use without a local executor, public directory submission
and the desktop interface were not verified.

## Reproducible evidence

```bash
bash tests/codex/test-basic.sh
bash tests/install-doctor/test-basic.sh
python3 -B tests/codex/cli-smoke.py
python3 -B tests/codex/install-smoke.py
```

The adapter suite uses real stdio messages for initialization, catalog discovery
and MCP calls. It checks relocation with spaces/metacharacters, nested cwd, stale
variables, AST analysis without imports, successful/failed Python compilation,
shell-payload rejection and wrapper argument/exit propagation. It requires exactly
16 skills and seven tools, and checks `initialize_project` refusals without
creating projects or making network calls.

The optional protocol smoke requires an installed Codex executable but no
authentication or models. It creates a temporary CODEX_HOME and catalog, uses
`plugin/read` to read skills and hooks, and registers MCP only in temporary
configuration. It starts an empty thread and calls `analyze_project`; an allowlist
excludes `turn/start` and `plugin/install`. It does not install the plugin or touch
global configuration.

Local verification with Codex CLI 0.167.1 (2026-11-11) passed with 16 skills, zero
hooks and seven tools. The adapter regressions exercise the protocol, forwarded
variables, signal handling and limits. The separate install-smoke test verifies installation
and listing in temporary state and removes its registry on exit. Neither smoke
validates semantic skill selection or the desktop interface. Doctor regressions
check absence of mutations, dependencies that would fail if imported, inconsistent
versions, missing exports, invalid JSON, escaping paths and probe limits.

## Official sources consulted

- [Package your plugin](https://developers.openai.com/plugins/build/plugins):
  compatibility overlay, internal paths and explicit hooks replacing default discovery.
- [OpenAI plugin guide](https://learn.chatgpt.com/docs/plugins): distribution and
  differences between execution surfaces.
- [Plugins in Agents API](https://developers.openai.com/api/docs/guides/agents-api/tools/plugins):
  examples of `skills` and `mcpServers` in the compatibility manifest.

Sources consulted on 2026-10-31. `codex --help`, `codex plugin --help`,
`codex plugin add --help` and `codex plugin marketplace add --help` confirmed the
local 0.166.0 interface (the 2026-11-11 recipe run used 0.167.1). Installation was
tested only in temporary state; no global configuration changed and no publication,
authentication or model-turn commands ran.
