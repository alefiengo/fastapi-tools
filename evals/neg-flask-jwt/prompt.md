---
description: Flask JWT hardening must not activate FastAPI components.
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Our Flask API validates JWTs with PyJWT. How should we pin the allowed algorithms, audience and issuer?
