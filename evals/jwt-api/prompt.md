---
description: Validate JWT and ownership in FastAPI.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Review JWT auth for FastAPI: code decodes tokens with verify_signature=False and accepts owner_id from the request payload to approve an order. Show required fixes and tests.
