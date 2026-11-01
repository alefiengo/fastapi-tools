---
type: llm
---

PASS explains one AsyncSession per concurrent task, rollback before failed-session
reuse, explicit relationship loading and explicit lifespan management for HTTPX.
Requires a real failure after a flushed write and observation via an independent
transaction rather than mocks or fixture teardown to prove rollback. Reports
triggers/evidence and does not claim measured performance or test execution.
FAIL for global session reuse, automatic sync-to-async conversion, implicit
HTTPX startup or rollback efficacy inferred only from a mock.
