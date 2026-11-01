# Maintaining fastapi-tools

This repository distributes a FastAPI development plugin for Claude Code.
Read CONTRIBUTING.md and docs/architecture.md before changing executable behavior.
The agents/ and skills/ directories contain shipped product components, not the
maintenance team. Use docs/skills/repo-director/SKILL.md for requested coordination.
Preserve existing work; assign one writer per file before parallel edits.
Keep runtime/ authoritative for Python discovery and execution. Hooks and MCP
must delegate, not invent competing discovery or commands. Do not import user
application modules during static analysis or install dependencies during checks.
Validate executable changes with meaningful regressions and applicable checks.
Behavioral model evaluations require an explicit budget and authorization.
Publication and external changes require user authorization; follow existing
session authorization without repeated permission requests. Do not modify
other repositories or global configuration.
