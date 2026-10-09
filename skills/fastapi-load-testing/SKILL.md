---
name: fastapi-load-testing
description: Design and execute authorized k6/Locust load tests for FastAPI with measurable acceptance criteria.
---

# Load Testing for FastAPI

Establish the authorized target, representative dataset, auth strategy, arrival/concurrency model and numerical acceptance criteria before generating traffic. Prefer k6 or Locust already in the project. Never load-test production or external services by assumption.

Specify warmup, steady-state duration, request mix, p95/p99 latency, error-rate and throughput thresholds. Avoid averaging away slow endpoints. Keep functional assertions separate from performance thresholds and fail the process when acceptance criteria fail.

Measure a baseline, capture database pool and event-loop evidence, make one justified change, repeat the same workload and compare. Distinguish server capacity from load-generator saturation. Give each virtual user safe isolated records for writes; clean fixtures deliberately.

Report executed target, parameters, environment, percentile and failure evidence. A script proposal or short local smoke test cannot certify production capacity.
