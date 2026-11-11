---
description: An import cycle in a CLI package must not activate FastAPI components.
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Our Click-based CLI package has an import cycle between cli.commands and cli.config. How do we break it?
