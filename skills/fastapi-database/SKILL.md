---
name: fastapi-database
description: Design and troubleshoot SQLAlchemy/SQLModel persistence, sessions, SQL queries and Alembic migrations for FastAPI.
---

# Database for FastAPI

Inspect whether the project uses SQLAlchemy, SQLModel or another ORM; keep its established sync/async model. A session belongs to one request/unit of work. Choose a clear transaction owner and rollback on failures. With async sessions, avoid implicit lazy loads during serialization and avoid sharing a session across concurrent tasks.

Use database constraints for invariants and explicit transactions for multi-write operations. Test a failure after the first write to establish atomicity; observe final state through a fresh independent session. SQLite cannot prove PostgreSQL locking, data types or isolation behavior.

Alembic revisions use literal `revision` and `down_revision`, not a filename version convention. Review generated migrations, rename operations, backfills, lock duration and downgrade feasibility. Applied revisions are immutable. Introduce a new revision for corrections; inspect `depends_on`, branches and merge heads.

```bash
python -m alembic heads
python -m alembic history
# Database access: only when requested and target configuration is known.
python -m alembic current
# Applying changes requires authorization for that target database.
python -m alembic upgrade head
```

`check_migrations` defaults to static AST lint without importing env.py or connecting to the database. Explicit status mode runs current; it never applies upgrades. Autogenerate is a proposal and can miss renames and data transformations. Use expand/backfill/contract sequencing for rolling deployments.

`alembic check` is not this plugin's static lint: it executes the configured
migration environment and compares database schema with metadata using
autogenerate. It requires the appropriate target authorization and inherits
autogenerate's detection limits. Empty output is not proof that a backfill,
rename or rolling deployment is safe. A failed SQLAlchemy flush requires an
explicit rollback before the same Session can be reused.

References: https://alembic.sqlalchemy.org/en/latest/autogenerate.html and
https://docs.sqlalchemy.org/en/20/orm/session_basics.html
