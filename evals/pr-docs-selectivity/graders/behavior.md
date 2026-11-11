---
type: llm
---

PASS keeps the review scoped to the prose change, reports spelling findings or
an empty findings list, and states that no application verification was needed.
FAIL if it claims tests, builds or other checks ran, or reports application,
dependency or deployment findings for files the PR does not change.
