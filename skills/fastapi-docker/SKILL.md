---
name: fastapi-docker
description: Package a FastAPI application in Docker/Compose and diagnose its container startup, persistence or image CI issues. Not for containers of other frameworks.
---

# Docker for FastAPI

Inspect the application's actual entry point, dependency manager, database driver and Python requirement. Build dependencies from a lockfile or pinned requirements. Take the base image's Python version from `requires-python`. Run as a non-root user, bind Uvicorn to 0.0.0.0 and use exec-form CMD for signals. Do not use development reload in production. Behind a TLS-terminating proxy, add `--proxy-headers` and set `--forwarded-allow-ips` to the proxy's addresses; Uvicorn trusts only 127.0.0.1 by default, so redirects and `request.url` otherwise report the wrong scheme or client.

```dockerfile
# Example for a project with pinned requirements.txt and app/main.py.
FROM python:3.14-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN useradd --uid 10001 --create-home appuser
COPY --chown=appuser:appuser app ./app
USER appuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```dockerfile
# Example for a uv project with uv.lock and app/main.py; .dockerignore excludes .venv.
FROM python:3.14-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.7 /uv /bin/
ENV UV_PYTHON_DOWNLOADS=0 UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev

FROM python:3.14-slim
RUN useradd --uid 10001 --create-home appuser
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app
ENV PATH="/app/.venv/bin:$PATH"
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: "postgresql+psycopg://app:${DB_PASSWORD:?set DB_PASSWORD}@db:5432/app"
    depends_on:
      db:
        condition: service_healthy
  db:
    image: postgres:18
    environment:
      POSTGRES_DB: app
      POSTGRES_USER: app
      POSTGRES_PASSWORD: "${DB_PASSWORD:?set DB_PASSWORD}"
    volumes: ["pgdata:/var/lib/postgresql"]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 5s
      timeout: 3s
      retries: 10
volumes:
  pgdata:
```

For PostgreSQL 18+, persist /var/lib/postgresql; inspect existing volume/version before upgrading. Use the driver the application declares. Add .dockerignore for .git, .venv, secrets and caches. Run migrations once as an explicit release job rather than racing every worker. Startup dependency ordering does not replace retries or readiness checks. FastAPI has no built-in /health: implement and configure actual probes.
