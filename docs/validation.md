# Validation for FastAPI Tools 0.4.0

This report describes the 0.4.0 release as published on 2026-11-11. Re-run the
commands in CONTRIBUTING.md to validate a newer snapshot.

Release validation is performed on the snapshot identified by its annotated tag.
The attached GitHub release report records the exact commit, executed commands,
results and environment. See [contributing](../CONTRIBUTING.md) for reproduction.

Documentation-only corrections may reuse recorded functional results when all
implementation, configuration, fixture and test files are byte-identical. The
release report identifies the original validation commit and distinguishes reused
results from checks rerun on the corrected snapshot.

Static inspection never imports application modules. Checks execute code from
trusted projects. Functional tests establish their observed behaviors, not model
activation, skill efficacy or production performance. No paid behavioral
evaluations are part of functional release validation.

The validated platform is Linux on WSL2. macOS, native Windows, desktop
interfaces, PostgreSQL and a multi-version Node/Python matrix are not established
by these checks. Native Windows is unsupported by the POSIX runtime. Project
initialization on a WSL Windows drive (`/mnt/c`) is refused with an explicit
message. Claude's optional public-directory icon warning does not invalidate local
strict validation.

## Executed checks

- 13 deterministic suites passed with Python 3.12.15 and again with Python 3.11.17.
- Eleven executable FastAPI/Pydantic/SQLAlchemy/Alembic examples passed with the
  pinned set and with the latest releases (Python 3.14.4, FastAPI 0.162.4,
  Pydantic 2.14.3, SQLAlchemy 2.1.8).
- Four real ecosystem scenarios passed: generated project, Python/venv, uv and Poetry.
- Node/Python syntax checks and strict Claude plugin, skills, agents and
  `docs/skills` validation passed.
- Production npm audit reported zero vulnerabilities for the locked dependencies.
- The MCP server answered `initialize` and listed seven tools on Node 20.3.0.
- Codex CLI 0.167.1 read 16 skills, zero hooks and seven tools, and called the MCP.
- Local Codex installation/listing passed with disposable CODEX_HOME state.
- A Claude Code 2.1.322 marketplace install from a git source in isolated
  configuration created the root `node_modules` and connected the MCP server.
- The offline installation doctor passed on a FastAPI fixture.

Environment: Linux x86_64 (WSL2), Node 24.21.0, runtime Python 3.12.15, uv
0.13.0, Poetry 2.5.1, FastAPI 0.162.0, Pydantic 2.14.2, pytest 9.2.0, Ruff
0.17.3, mypy 2.4.1, SQLAlchemy 2.0.55 and Alembic 1.20.1.

The ecosystem fixtures use valid empty locks and previously installed tools
exposed to private environments. They do not test remote dependency resolution or
complete application lock fidelity. SQLite checks do not establish PostgreSQL
behavior. Host protocol and installation smokes do not measure model selection
or response quality. The evaluation harness, its MCP mocks and negative cases were
checked offline only. No paid behavioral evaluations were run.
