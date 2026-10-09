---
description: Review rolling migration safety.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Review an Alembic migration that renames orders.owner to owner_id and immediately removes the old column while old FastAPI workers still run. Provide release gates.
