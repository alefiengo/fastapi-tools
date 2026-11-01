---
name: fastapi-pr-review
description: Review a FastAPI change with relevant specialist reviewers, one coordinated verification gate and an evidence-based verdict. Use when explicitly asked to review a FastAPI PR or diff.
disable-model-invocation: true
---

# FastAPI PR review

Inspect the diff, project conventions and supplied results. Prose-only changes need no application gate. For application changes run or reuse one equivalent full-root `run_build` verify; share its results with reviewers rather than launching concurrent duplicate checks.

Select only relevant roles: fastapi-code-reviewer for behavior/auth/contracts; fastapi-runtime-reviewer for sessions, concurrency, queries and lifecycle; fastapi-migration-reviewer for Alembic changes; fastapi-docker-reviewer for images, deployment and CI. If agent tools are available, delegate selected read-only reviews with the diff, files and verification results. Otherwise perform the same scoped review directly. fastapi-test-writer writes tests only when requested, not as an automatic review side effect.

Deduplicate cross-domain findings. Report severity, file/line, concrete trigger, consequence, evidence and smallest useful correction. A blocker requires demonstrated broken behavior, security exposure or data loss. Label hypotheses and missing evidence. A passed test suite does not prove an untested behavior correct. Empty findings are valid; omit style-only complaints.

Deliver the verdict, actionable findings and verification status. Never claim tests, broker publication, database checks or performance runs that were not executed. Respect the user's existing architecture and authorization.
