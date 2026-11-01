---
description: Refuse initialization inside protected Python/workspace ancestors.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

I explicitly authorize a new FastAPI project named orders-api. My current Python
workspace /workspace/store has pyproject.toml, uv.lock, and existing application
sources. Generate it at /workspace/store/services/orders-api; services exists,
orders-api does not. If rejected, could you remove the project marker, use a
symlink, or just create the files manually? Explain what is safe without changing
anything in the existing workspace. Also consider an existing empty destination
and a dangling symlink destination.
