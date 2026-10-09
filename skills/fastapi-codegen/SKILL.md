---
name: fastapi-codegen
description: Generate FastAPI routers, Pydantic schemas, dependencies, services and SQLAlchemy persistence code. Use for endpoint and feature implementation in FastAPI.
---

# Codegen for FastAPI

Inspect existing naming, layout, dependency providers, models, persistence API and errors first. Extend these conventions rather than imposing a new repository layer. Generate complete imports and mounted routers. Use Pydantic v2 only when the installed version supports it.

For mutations, validate input, authorize the current user for the object, execute the transaction, and serialize only public output fields. Never accept owner_id from an untrusted payload as authorization. Bound pagination and sort deterministically. Enforce uniqueness in the database and map known integrity failures to the established conflict response.

Keep blocking I/O out of async def routes. A sync route can use the existing synchronous database session; async routes should await async drivers. Do not share AsyncSession across requests or concurrent tasks. Ensure dependency cleanup on failure.

```python
from typing import Annotated
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix="/products", tags=["products"])

class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)

class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str

# Supply get_service from the application's dependency module.
# Mount with app.include_router(router, prefix="/api/v1").
```

Do not present placeholder service implementations as a finished feature. Deliver mounted routes, schemas, integration with actual services and tests for observable successes, validation, absence and access rules. Avoid modifying applied Alembic revisions.
