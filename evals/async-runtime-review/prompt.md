---
description: Review SQLAlchemy transaction and ASGI lifecycle evidence.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Ask fastapi-runtime-reviewer to review this proposed FastAPI pattern: one global
AsyncSession is shared by every request and both tasks in asyncio.gather. After
an IntegrityError on flush the same session is reused without rollback. The
response uses Pydantic from_attributes on unloaded relationships. Our test only
asserts mock_session.rollback.called, and AsyncClient(transport=ASGITransport(app))
is assumed to start lifespan. Identify concrete triggers and propose meaningful
tests without changing files or claiming they have been executed.
