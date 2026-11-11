---
description: Write async FastAPI tests that manage lifespan explicitly.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Our FastAPI app opens an asyncpg pool in its lifespan and stores it in
app.state.pool. Show pytest tests for GET /orders/{id} using httpx.AsyncClient
with ASGITransport, including a dependency override for the current user that
does not leak into other tests. Do not change production code.
