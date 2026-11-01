---
name: fastapi-observability
description: Diagnose FastAPI logs, metrics, traces and application readiness/liveness. Use for instrumentation and operational diagnosis.
---

# Observability for FastAPI

Inspect existing instrumentation and log configuration first. Use request/correlation IDs, structured logs and exception context without logging secrets, tokens, passwords or request bodies by default. Keep metric labels bounded; raw paths, user IDs and exception messages can create excessive cardinality.

Separate liveness (process/event-loop functioning) from readiness (able to serve traffic and required dependencies available). Implement endpoints if the application needs them: FastAPI does not ship Actuator or built-in health routes. Report unavailable checks honestly; do not advertise readiness without checking required dependencies.

Use `app_health` with explicit configured paths. Defaults are /health, /health/ready and /health/live on port 8000. 401/403 indicate access denial, 404 indicates an absent or differently mounted route; neither proves application health. Do not forward credentials automatically.

Manage clients and pools through the app lifespan context, closing them on shutdown. Instrument ASGI/SQLAlchemy using the project's compatible OpenTelemetry packages; avoid double instrumentation. Test startup, shutdown and failed dependency checks. Export traces to the configured collector and verify an actual request span before claiming success.

Reference: https://fastapi.tiangolo.com/advanced/events/
