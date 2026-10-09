---
description: Inspect Alembic revision metadata and history.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

My FastAPI project has alembic/versions/add_index.py with revision = None, down_revision = "abc" and upgrade() calling op.create_index. Is the file correct? Show the minimum fix without connecting to the database.
