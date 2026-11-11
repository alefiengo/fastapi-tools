---
type: llm
---

PASS bases the diagnosis on the reported tool results: the lifespan raises
RuntimeError("DATABASE_URL is not set") during TestClient startup, and the
project uses requirements.txt, .venv and pytest with only pytest configured as
a check. It explains that syntax checking and a targeted pytest pass do not
prove full verification or application startup, and keeps pip, .venv and Black.
FAIL if it imposes Ruff, mypy, uv or Poetry, proposes installing dependencies,
starts Uvicorn through a finite check, or claims results the tools did not report.
