---
description: Event-loop blocking in a non-FastAPI asyncio program must not activate FastAPI components.
max_turns: 6
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Our aiohttp-based web scraper (no web framework) stalls because a CPU-heavy parse runs inside the event loop. How do we find and fix the blocking call?
