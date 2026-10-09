# Contributing

Keep the plugin focused on FastAPI development and the application's existing
conventions. Match skill/agent frontmatter names to directories/files. Reviewers
use Read, Glob and Grep only; designers and test writers have scoped output.

Shared discovery, inventories and coordinated execution belong in runtime/;
hooks remain inexpensive until Stop. MCP validates inputs, bounds outputs and
distinguishes static evidence from executed checks. Keep plugin, marketplace,
MCP package/lock and server versions aligned. Update catalogs when renaming tools.

```bash
npm ci --prefix mcp-server
node --check mcp-server/index.js
python3 -m py_compile runtime/project_runtime.py hooks/scripts/hook-runtime.py
bash tests/run-all.sh
git diff --check
```

Deterministic tests use temporary Python projects, controlled executable fixtures,
real stdio MCP messages and local HTTP listeners. Add meaningful regressions for
execution, scope, cache freshness, failure/cancellation and coordination changes.
Validate the real FastAPI example separately:

```bash
python3 -m pip install -r tests/examples/requirements.txt
bash tests/examples/check.sh
```

CI runs deterministic checks on Linux/macOS and Python examples separately.
Behavioral evaluations require a logged-in Claude account and paid model calls;
run only when explicitly requested. Keep reports local, retain failures, and use
one frozen response when comparing judges. See evals/README.md.

Use Conventional Commits. PR descriptions explain resulting behavior, validation
and material limitations. Validate the plugin in a trusted FastAPI project with
claude --plugin-dir /absolute/path/to/this/repo when interactive checks are needed.

## GitHub publication

The intended destination is `alefiengo/fastapi-tools`. Before the first push,
create that repository and point this checkout's origin to its URL. A copied
checkout may still point to spring-boot-tools; inspect `git remote -v` first.
Include new FastAPI skills, agents, evaluations and fixtures in the commit,
along with deletions of the old framework files. Never publish node_modules,
virtual environments, local state or evaluation reports.

Validate a clean copy with `npm ci --prefix mcp-server`, the deterministic suites,
example tests, strict Claude plugin validation and `npm audit --omit=dev` in
mcp-server. After pushing, require the four deterministic matrix checks and the
examples check to pass on GitHub before creating a release. Local checks do not
establish Linux/macOS or Node version matrix results.

Enable private vulnerability reporting before using the security contact link.
Configure a main ruleset with required CI checks, resolved review conversations
and an up-to-date branch according to the team's policy. Allow squash/rebase and
automatically delete merged branches if following the analogous Spring Boot repo.
These are GitHub settings, not properties guaranteed by files in this checkout.

For a tagged release, keep the plugin/marketplace/MCP versions aligned and ensure
the tag identifies the verified FastAPI commit. Create the GitHub release after
that commit's checks pass; add a release badge only once a release exists.
