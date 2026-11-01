---
description: Keep architecture and API design outputs scoped.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Ask fastapi-architect and fastapi-api-designer for a plan and HTTP contract for a
small existing FastAPI app with one products APIRouter and request-scoped sync
SQLAlchemy Session. A product has id, name, owner_id and internal_cost; only id
and name are public. Mutations require the authenticated owner. Propose the
smallest design, transaction owner, 404/403 convention and pagination contract.
Do not implement code or require new layers, an async ORM or extra tools.
