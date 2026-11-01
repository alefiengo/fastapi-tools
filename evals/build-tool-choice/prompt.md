---
description: Preserve configured Python tools and shared verification.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

We have FastAPI with requirements.txt, .venv, pytest and Black. No uv.lock,
poetry.lock, Ruff or mypy configuration exists. Help diagnose a startup lifespan
exception and verify changes using the plugin. Do not install anything, change
package managers or run a persistent server inside a finite build tool. Explain
what compile and a targeted pytest pass actually establish.
