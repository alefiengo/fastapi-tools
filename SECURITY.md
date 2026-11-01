# Security Policy

Report vulnerabilities through [private reporting](https://github.com/alefiengo/fastapi-tools/security/advisories/new).
Include reproduction, component and impact. Keep credentials and exploitable
details out of public issues.

Checks use allowlisted tasks and argument arrays without a shell. Application
tests, configuration, plugins and Alembic env.py still execute project code.
Use trusted projects. Static inventories do not import application modules;
explicit migration status executes current and never applies revisions.

Secret and DDL guards inspect common proposed Write/Edit patterns. They are
review aids, not complete scanners or an enforcement boundary. External writes
and arbitrary Python constructs require independent review. HTTP probes forward
no credentials and reject redirects; callers select intended destinations.

Verification records optimize unchanged successful checks. External services or
installed dependency changes may require force:true. The release validation
report records actual local checks and limits. Actions and automated Dependabot
updates are disabled; vulnerability alerts and secret scanning remain enabled.

Behavioral evaluations send context to a model provider and require an explicit
budget and authorization. Keep results local and inspect them before sharing.
