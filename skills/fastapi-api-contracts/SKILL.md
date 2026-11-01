---
name: fastapi-api-contracts
description: Design and review FastAPI request/response contracts, HTTP errors, pagination and OpenAPI. Use for API design or compatibility work in a FastAPI project.
---

# Api Contracts for FastAPI

Define routes, status codes, authentication, authorization and validation before implementation. Reuse the application's error envelope and distinguish missing resources from denied ownership. Inspect the generated OpenAPI schema and existing clients before changing optionality, aliases or enum values.

Use separate Pydantic input and output models. Explicit response models prevent accidental disclosure of persistence/internal fields. For ORM output use `ConfigDict(from_attributes=True)` with Pydantic v2, and ensure relationships are loaded before serialization. Prefer bounded pagination with deterministic ordering; clarify whether clients expect offset or cursor semantics. Keep Decimal, datetime and UUID wire representations consistent with the existing contract.

FastAPI normally returns validation failures with status 422 and a `detail` array; do not replace that envelope unless the project requires it. Explicitly describe additional error responses when clients depend on them. Runtime `/openapi.json` is stronger evidence than the static route inventory. Hidden endpoints and mounted subapplications need separate inspection.

Deliver a route table, payload examples, error cases and compatibility impact. Add tests for both successful serialization and rejected input.
