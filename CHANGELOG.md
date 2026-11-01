# Changelog

## Unreleased

- State project independence explicitly: FastAPI Tools has its own dependencies,
  roadmap, maintenance, versioning and releases; Spring Boot Tools is not required.
- Correct root documentation: measured platform coverage, namespaced Claude review
  command, fingerprint exclusions, agent instruction boundaries, interrupted staging
  cleanup, isolated example preparation, project provenance and version history.
- Document the intentional 0.1.0 to 0.3.0 numbering jump. No 0.2.0 tag or release
  existed. Keep published tags and their source contents intact.

## [0.3.0] - 2026-10-31

During release preparation, this number was selected to match an external Spring
Boot comparison reference. That was an unnecessary numbering choice for this
independent project. The preceding FastAPI tag was v0.1.0; no v0.2.0 was created.
Versions, capabilities and validation belong to FastAPI Tools independently.

- Add explicit local FastAPI initialization with protected ancestors, staging and
  exclusive publication; keep generation separate from dependency installation.
- Share 16 skills and seven MCP tools with Codex through a local adapter, with
  host-specific behavior documented and offline installation diagnostics.
- Harden shared Python verification and Alembic risk inspection, honor declared
  tools, and expand real venv/uv/Poetry/FastAPI integration evidence.
- Add maintenance direction, offline ablation tooling and a component evidence
  inventory without claiming unmeasured behavioral benefit.
- Update the vulnerable Zod resolution; remove repository Actions workflows,
  badges and Dependabot automation while preserving application CI guidance.
- Document architecture, compatibility, upgrades, security and local release evidence.

## [0.1.0] - 2026-10-08

Initial FastAPI adaptation for Claude Code, with skills, specialist agents, hooks,
MCP and a shared Python runtime. Tag v0.1.0 identifies commit
2887440a9ecfe211142d28a4ab28ba70ddd13908. This tag existed before 0.3.0; it did
not have a GitHub Release entry when 0.3.0 was published.

[0.3.0]: https://github.com/alefiengo/fastapi-tools/releases/tag/v0.3.0
[0.1.0]: https://github.com/alefiengo/fastapi-tools/tree/v0.1.0
