---
name: fastapi-performance
description: Investigate FastAPI latency, event-loop blocking, SQL query behavior, pools and caching using measured evidence.
---

# Performance for FastAPI

Collect a reproducible slow request, trace/profile or query evidence before changing code. Establish percentile latency and throughput with a consistent workload. Separate CPU work, network waiting, database query count, pool starvation and serialization cost.

Blocking database/file/network calls inside async def block the event loop unless deliberately offloaded. A synchronous route runs through FastAPI's threadpool; switching to async does not automatically accelerate it. Keep AsyncSession scoped per request/task. Inspect N+1 with SQL logs or query counters and choose eager loading for specific access patterns.

Bound result sets and pagination. Add indexes based on real query plans and production-sized data; quantify lock and write impact. Size pools across all workers, accounting for the database's connection limit. Caches require ownership/tenant-safe keys, invalidation and evidence of reuse.

Report baseline, identified cause, focused fix, repeated measurements and unresolved uncertainty. Do not infer improvements from code shape or add infrastructure without evidence.
