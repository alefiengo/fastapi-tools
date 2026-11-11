---
description: A SQLAlchemy/Alembic batch job without FastAPI must not activate FastAPI components.
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Our nightly ETL script is plain Python with SQLAlchemy 2 Core and Alembic, without any web framework. Show an Alembic revision that adds an index on events.created_at.
