---
description: Use Python module-boundary evidence.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Review boundaries in a FastAPI modular monolith. orders imports payments.models and payments imports orders.main.app. How can we remove the cycle and prevent private-module imports?
