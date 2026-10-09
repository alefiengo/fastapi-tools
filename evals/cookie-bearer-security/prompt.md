---
description: Distinguish cookie and bearer CSRF surfaces.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Our FastAPI app accepts either an HttpOnly session cookie or an Authorization bearer token. CORS allows our frontend. Do we need CSRF protection? Review both flows.
