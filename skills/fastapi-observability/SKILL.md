---
name: fastapi-observability
description: Diagnose FastAPI application logs, metrics, traces and readiness/liveness probes. Use for instrumentation and operational diagnosis of a FastAPI service; not for other Python processes.
---

# Observability for FastAPI

Inspect existing instrumentation and log configuration first. Use request/correlation IDs, structured logs and exception context without logging secrets, tokens, passwords or request bodies by default. Keep metric labels bounded; raw paths, user IDs and exception messages can create excessive cardinality.

Separate liveness (process/event-loop functioning) from readiness (able to serve traffic and required dependencies available). Implement endpoints if the application needs them: FastAPI does not ship Actuator or built-in health routes. Report unavailable checks honestly; do not advertise readiness without checking required dependencies.

Use `app_health` with explicit configured paths. Defaults are /health, /health/ready and /health/live on port 8000. 401/403 indicate access denial, 404 indicates an absent or differently mounted route; neither proves application health. Do not forward credentials automatically.

Manage clients and pools through the app lifespan context, closing them on shutdown. FastAPI 0.142.0+ emits OpenTelemetry traces, metrics and logs natively through the configured providers (`FastAPI(telemetry={...})`, with `exclude` for health routes); since 0.143.0 exporter auto-setup is opt-in via `FASTAPI_OTEL_AUTO_CONFIGURE=true`. Prefer it over `opentelemetry-instrumentation-fastapi` on those versions; FastAPI disables its native request telemetry when the contrib ASGI middleware is present, so keep only one. Older versions use the contrib package. Instrument SQLAlchemy with its own compatible package. Native exception logs include messages and stack traces that can contain sensitive data; filter them or set `logs` to False. Test startup, shutdown and failed dependency checks. Export traces to the configured collector and verify an actual request span before claiming success.

References: https://fastapi.tiangolo.com/advanced/events/ and
https://fastapi.tiangolo.com/advanced/opentelemetry/
