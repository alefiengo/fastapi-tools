---
name: fastapi-codegen
description: Generate FastAPI routers, Pydantic schemas, dependencies, services and SQLAlchemy persistence code. Use for endpoint and feature implementation in FastAPI.
---

# Codegen for FastAPI

Inspect existing naming, layout, dependency providers, models, persistence API and errors first. Extend these conventions rather than imposing a new repository layer. Generate complete imports and mounted routers. Use Pydantic v2 only when the installed version supports it.

For mutations, validate input, authorize the current user for the object, execute the transaction, and serialize only public output fields. Never accept owner_id from an untrusted payload as authorization. Bound pagination and sort deterministically. Enforce uniqueness in the database and map known integrity failures to the established conflict response.

Keep blocking I/O out of async def routes. A sync route can use the existing synchronous database session; async routes should await async drivers. SQLAlchemy 2.1+ no longer installs greenlet by default: AsyncSession needs `sqlalchemy[asyncio]` (or a driver extra such as `sqlalchemy[postgresql-asyncpg]`) declared in the project. Do not share AsyncSession across requests or concurrent tasks. Ensure dependency cleanup on failure.

```python
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field

# Illustrative import: use the application's existing service and provider.
from app.products.service import ProductService, get_service

router = APIRouter(prefix="/products", tags=["products"])
Service = Annotated[ProductService, Depends(get_service)]


class ProductCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ProductRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


@router.get("", response_model=list[ProductRead])
def list_products(
    service: Service,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    return service.list(limit=limit, offset=offset)  # Service orders deterministically.


@router.get("/{product_id}", response_model=ProductRead)
def get_product(product_id: int, service: Service):
    product = service.get(product_id)
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
    return product


@router.post("", response_model=ProductRead, status_code=status.HTTP_201_CREATED)
def create_product(payload: ProductCreate, service: Service):
    return service.create(payload)


# Mount with app.include_router(router, prefix="/api/v1").
```

Do not present placeholder service implementations as a finished feature. Deliver mounted routes, schemas, integration with actual services and tests for observable successes, validation, absence and access rules. Avoid modifying applied Alembic revisions.
