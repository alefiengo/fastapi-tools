---
description: Preserve Pydantic v2 requiredness and serialized contracts.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Our FastAPI project already uses Pydantic v2. A migration changed a request field
to `note: str | None` with no default and kept an output `price: Decimal`.
Clients omit note and expect price as a JSON string. A validator raises TypeError
on invalid values. Review compatibility and propose tests for absent note, null,
bad input and Decimal output. For ORM output we use AsyncSession and unloaded
relationships with from_attributes=True. Do not upgrade packages or replace the
ORM. Describe which claims need executing the app's actual tests.
