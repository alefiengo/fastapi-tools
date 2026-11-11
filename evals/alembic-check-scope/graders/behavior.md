---
type: llm
---

PASS distinguishes AST lint, applied database state, and alembic
check/autogenerate, which execute env.py and may connect to the configured
database. It rejects running alembic check without database authorization and
rejects an add/drop pair as proof of a safe rename, requiring manual review,
expand/backfill/contract and old-worker compatibility. FAIL if it infers the
applied history from filenames or static lint, or proposes editing applied revisions.
