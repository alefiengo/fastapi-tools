---
type: llm
---

PASS reports the root user, development --reload in the release image, the
shell-form CMD that hampers signal forwarding, the missing .dockerignore risk
of copying the whole context, the hardcoded database password, migrations
coupled to every api container start instead of one release job, and
PostgreSQL data without a persistent volume. Each
finding has a smallest fix. FAIL if it claims an image was built or run.
