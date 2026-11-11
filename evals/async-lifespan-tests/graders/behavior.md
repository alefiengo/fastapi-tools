---
type: llm
---

PASS explains that ASGITransport does not run lifespan and manages it
explicitly (an existing fixture, LifespanManager or TestClient as a context
manager), restores app.dependency_overrides in teardown and uses an AnyIO or
asyncio test marker compatible with the project. FAIL if it assumes AsyncClient
starts lifespan, leaves overrides in place, changes production code or claims
the tests ran.
