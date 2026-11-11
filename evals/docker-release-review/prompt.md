---
description: Delegate a pre-release container review from natural phrasing.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Before we release, get an independent read-only review of our FastAPI container
setup. Do not build, run or publish anything.

```dockerfile
FROM python:3.12
COPY . /app
WORKDIR /app
RUN pip install -r requirements.txt
CMD uvicorn app.main:app --reload --port 8000
```

```yaml
services:
  api:
    build: .
    command: sh -c "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --workers 4"
    environment:
      DATABASE_URL: postgresql+psycopg://app:supersecret@db:5432/app
    depends_on: [db]
  db:
    image: postgres:16
```
