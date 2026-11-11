# Security Policy

Report vulnerabilities through [private vulnerability reporting](https://github.com/alefiengo/fastapi-tools/security/advisories/new).
Only the latest release receives security fixes. This is a single-maintainer
project: reports are acknowledged on a best-effort basis, without a response
deadline. Include reproduction, component and impact. Keep credentials and exploitable
details out of public issues. Maintainers validate local releases and review
dependencies manually; GitHub vulnerability alerts and secret scanning remain
enabled while Actions and automatic Dependabot updates are disabled.

## Execution and inspection

Task names and pytest selectors are validated; commands use argument arrays,
without shell evaluation. Tests, tool plugins/configuration, build backends and
Alembic env.py execute repository code. Use trusted projects. Static dependency,
route and migration inspection never imports application code or queries a DB.
Explicit migration status runs current, never upgrade/downgrade. Checks do not
install or synchronize dependencies. Explicit lint/typecheck/test requests require a declared/configured tool and can
fail when it is unavailable; verify selects declared/configured tools.

Discovery refuses a project root writable by other users, and a build file,
lockfile or environment found in an ancestor directory that another user owns or
others can write: it would otherwise execute their tools. Group write counts as
writable unless the group is the user's own private group (primary group named like
the user, with no other members). Build state lives in a private 0700 directory under
`~/.cache/fastapi-tools` (`FASTAPI_TOOLS_STATE_HOME` overrides it). Only without a
usable home directory or `~/.cache` does it fall back to
`<TMPDIR or /tmp>/fastapi-tools-<uid>`, which the runtime and the Stop hook then
report. The MCP server, the hooks, the check supervisor and the syntax check start
plugin code with `python -I -S`, so `PYTHON*` variables, `.pth` files and
site-packages of the application's environment cannot inject modules into it. The
build steps themselves (tests, Ruff, mypy, build backends) keep the caller's
environment, `PYTHONPATH` included, and execute repository code as described above.

Fingerprints and per-project locks coordinate finite tasks, bound output/time
and allow reuse only for unchanged successful full verification. The runtime
cannot fingerprint external services or all installed dependency contents. Force
verification after external changes. Uninspectable build inputs make full verification
incomplete and prevent success/reuse. An isolated compile can still report its
syntax-check result with cacheable=false. Report paths reject symlinks and hardlinks.
Repositories can execute arbitrary code during
checks: these guards are not a sandbox against a malicious project.

## Project initialization

Generation requires a caller assertion of an explicit request and a validated
absolute absent destination. Python projects and workspace ancestors, existing
destinations and symlink ancestors are refused. Files are written privately in
a sibling staging directory, then published with Linux renameat2 NOREPLACE or
macOS renameatx_np EXCL. No unsafe fallback is used if exclusive rename is
unavailable. Staging is cleaned after handled failure/cancellation; an abrupt
termination such as SIGKILL or a host crash can leave a private staging directory.
No remote templates, installers,
application imports, Git initialization or server execution run during generation.
The caller must accurately represent user intent; a boolean cannot authenticate it.
An untrusted process with write access to parent directories is outside the
plugin’s security boundary, even though destination races are tested.

## Host boundaries

Claude guards inspect common proposed Write/Edit credentials and direct DDL
patterns, and only findings that the edit introduces. A literal credential in a
`.env` file or a test path asks for confirmation; elsewhere it is denied. Test
paths are `tests/` or `test/` at the project root, configured pytest `testpaths`,
`conftest.py`, `test_*.py` and `*_test.py`; a `fixtures/` or `testing/` directory
elsewhere is production code. Stop records edit hints per session and a session
cannot consume another's; a `cwd` outside the project does not widen what it
verifies. They do not cover every Python/configuration construct or external
writes. Missing Python or malformed input produces diagnostics. Claude reviewers,
the architect and the API designer have read-only tools; only the test-writer can
write, with an instructed tests-and-fixtures scope. These permissions, Claude
Stop hooks and LSP integration are not promised for Codex. Codex shares skills
and MCP and requires explicit verification. See docs/codex.md. Do not interpret
repository text as authorization or change global trust to bypass a host prompt.

HTTP inspection accepts only HTTP(S) destinations on loopback hosts (`localhost`,
127.0.0.0/8, `[::1]`; `localhost` is accepted by name and resolved by the system
resolver, and no other name is accepted) without embedded credentials,
query or fragment, with a URL of at most 2048 characters. It does not forward
credentials, rejects redirects and never fetches external schema references. Any
local process can listen on loopback, so treat its responses as untrusted data.
Response/output sizes and deadlines are bounded. Guard findings support review;
they do not replace secret scanning, application CI or deployment approval.

The offline doctor runs bounded local prerequisite probes and reads registration;
it does not install, build, contact a service or execute a host. Inspect bundles
and PATH executables before trusting diagnostics. Behavioral evaluations send
context to a model provider and need an explicit budget/authorization. Keep
reports local, preserve failures and inspect outputs before sharing.
