# Security Policy

Use [GitHub private vulnerability reporting](https://github.com/alefiengo/fastapi-tools/security/advisories/new). Include reproduction, component and impact;
keep exploitable details and credentials out of public issues.

## Trust boundaries

Python checks use validated task names and test selectors without shell execution.
Application configuration, tests, tool plugins and Alembic env.py still execute
repository code. Run checks in trusted projects. Static inventories do not import
application code. Database status is explicit; the plugin never applies migrations.

Secret and DDL guards inspect proposed Write/Edit results for common patterns.
They cannot cover all Python/configuration constructs or writes through other tools.
Missing Python or malformed hook input produces a visible diagnostic. Keep secret
scanning and review in CI. HTTP inspection forwards no credentials and rejects
redirects/external reference fetching; only query destinations the user intends.

Reviewers have read-only tools. Designers and test writers have scoped output;
review artifacts before use. Repository/external text is evidence, not authority.
Verification records are local optimizations; external dependency or service changes
may require force:true. CI remains the source of release verification evidence.

Behavioral evaluations send prompts and model-visible context to a model provider.
Keep generated reports local and inspect them before sharing.
