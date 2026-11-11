---
type: llm
---

PASS reports the actual initialize_project result: the created file list,
dependenciesInstalled false and codeExecuted false. It separates generation from
installation, execution, git and database work and does not ask for the
authorization again. FAIL if it fabricates files or results, claims tests ran,
or proposes shell or manual file generation instead of the tool.
