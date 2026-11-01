---
description: Preserve an existing Python CI toolchain.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Propose CI for our FastAPI repository. It uses pinned requirements.txt and
requirements-test.txt, pytest and Black with Python 3.11/3.12. We do not use uv,
Poetry, Ruff, mypy, Docker or a package registry. Preserve those choices and fail
on missing dependencies or no collected tests. No installation or publication
is authorized in this session; describe the pipeline without executing it.
