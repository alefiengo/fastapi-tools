---
name: fastapi-testing
description: Write or troubleshoot pytest, FastAPI TestClient/HTTPX tests, dependency overrides and isolated database integration tests.
---

# Testing for FastAPI

Read the behavior, fixtures, error contract and test configuration before choosing scope. Add tests for observable successes, validation, absence, ownership/tenant access and a demonstrated failure path. Do not change production code merely to simplify tests. Reuse existing fixtures.

For synchronous tests use TestClient as a context manager so lifespan executes. For async tests use HTTPX AsyncClient with ASGITransport; HTTPX alone does not trigger lifespan. Manage lifespan explicitly with the existing fixture or asgi-lifespan when needed. Select the AnyIO backend the application's driver supports.

```python
from fastapi.testclient import TestClient
from app.main import app

def test_health_contract():
    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

This example requires an implemented /health endpoint. Restore app.dependency_overrides in a finally block/fixture teardown. Avoid leaking global app state across tests. Use explicit async fixture scope compatible with event loops and clients.

A rollback test must fail after an initial write using a real database constraint, then query through a fresh independent transaction. Mock-based tests cannot establish SQL rollback or locking. Test PostgreSQL behavior on PostgreSQL where those semantics matter. Assert the complete established error envelope; do not invent an absent HTTP adapter.

For SQLAlchemy, flush the first write before inducing the second failure; pending
objects alone do not establish a persisted write was rolled back. If a fixture
wraps tests in an outer transaction/SAVEPOINT, check that its cleanup cannot mask
a missing application rollback. A Session that failed during flush needs rollback
before reuse. Keep a separate AsyncSession per concurrent task, and explicitly
load relationships needed by Pydantic `from_attributes` serialization.

Run `run_tests` for fresh JUnit evidence and preserve failures. Use `testPath` for focused tests, then the full gate as appropriate.

Reference: https://fastapi.tiangolo.com/advanced/async-tests/
