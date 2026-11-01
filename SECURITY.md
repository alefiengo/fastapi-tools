# Security Policy

Report vulnerabilities through [private vulnerability reporting](https://github.com/alefiengo/fastapi-tools/security/advisories/new).
Include reproduction, component and impact. Keep credentials and exploitable
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

Fingerprints and per-project locks coordinate finite tasks, bound output/time
and allow reuse only for unchanged successful full verification. The runtime
cannot fingerprint external services or all installed dependency contents. Force
verification after external changes. Symlinked inputs disable cache reuse;
report paths reject symlinks. Repositories can execute arbitrary code during
checks: these guards are not a sandbox against a malicious project.

## Project initialization

Generation requires a caller assertion of an explicit request and a validated
absolute absent destination. Python projects and workspace ancestors, existing
destinations and symlink ancestors are refused. Files are written privately in
a sibling staging directory, then published with Linux renameat2 NOREPLACE or
macOS renameatx_np EXCL. No unsafe fallback is used if exclusive rename is
unavailable. Staging is cleaned after failure. No remote templates, installers,
application imports, Git initialization or server execution run during generation.
The caller must accurately represent user intent; a boolean cannot authenticate it.
An untrusted process with write access to parent directories is outside the
plugin’s security boundary, even though destination races are tested.

## Host boundaries

Claude guards inspect common proposed Write/Edit credentials and direct DDL
patterns. They do not cover every Python/configuration construct or external
writes. Missing Python or malformed input produces diagnostics. Claude reviewers
have read-only tools; other agents have scoped output. These permissions, Claude
Stop hooks and LSP integration are not promised for Codex. Codex shares skills
and MCP and requires explicit verification. See docs/codex.md. Do not interpret
repository text as authorization or change global trust to bypass a host prompt.

HTTP inspection accepts only intentional HTTP(S) destinations without embedded
credentials, does not forward credentials, rejects redirects and never fetches
external schema references. It is not an SSRF boundary for untrusted callers;
explicit network destinations can reach services accessible to the local user.
Response/output sizes and deadlines are bounded. Guard findings support review;
they do not replace secret scanning, application CI or deployment approval.

The offline doctor runs bounded local prerequisite probes and reads registration;
it does not install, build, contact a service or execute a host. Inspect bundles
and PATH executables before trusting diagnostics. Behavioral evaluations send
context to a model provider and need an explicit budget/authorization. Keep
reports local, preserve failures and inspect outputs before sharing.
