---
description: Measure before tuning async or database behavior.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

A FastAPI API feels slow. Should we make every handler async, double workers and add Redis? We have no traces or query measurements yet.
