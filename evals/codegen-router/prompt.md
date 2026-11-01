---
description: Create mounted product routes with response models, bounded pagination and validation.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

I have a FastAPI project using Pydantic v2 and SQLAlchemy. Product has id, name, sku and Decimal price. Existing get_session provides a request-scoped synchronous Session. Create list (paginated), get-by-id and create routes under /api/v1/products. Reuse the existing error contract and test the behavior.
