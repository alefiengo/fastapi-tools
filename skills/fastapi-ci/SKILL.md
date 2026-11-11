---
name: fastapi-ci
description: Configure CI checks, dependency scanning and image publication for a FastAPI Python project. Use when asked to change FastAPI pipelines.
---

# Ci for FastAPI

Inspect repository scripts and supported Python versions. Preserve the existing package manager and lockfile. CI should install locked runtime and development dependencies, then run the same syntax/lint/type/test gates used locally. Missing test dependencies or no collected tests must fail. Publish packages or images only when explicitly requested.

For uv, synchronize with `uv sync --locked --group dev` after inspecting declared groups; `--locked` fails when uv.lock is out of date with pyproject.toml, while `--frozen` would silently install the stale lock. For a requirements project, use the repository's pinned requirements and separate development requirements. Do not invent a requirements-dev.txt that does not exist.

```yaml
# GitLab example for an existing uv project with a dev dependency group.
# Match the image's Python to requires-python; pin versions per repository policy.
stages: [verify, publish]
variables:
  UV_LINK_MODE: copy
verify:
  stage: verify
  image: ghcr.io/astral-sh/uv:0.13.7-python3.14-trixie-slim
  script:
    - uv sync --locked --group dev
    - uv run --no-sync python -m compileall -q app  # The actual source package.
    - uv run --no-sync ruff check .
    - uv run --no-sync mypy .  # Only when the project declares mypy.
    - uv run --no-sync pytest --junitxml=reports/pytest.xml
  artifacts:
    when: always
    reports:
      junit: reports/pytest.xml
image-build:
  stage: publish
  # Docker-in-Docker needs a privileged runner sharing /certs/client.
  image: docker:29.9.3-cli
  services: [docker:29.9.3-dind]
  variables:
    DOCKER_TLS_CERTDIR: "/certs"
  rules:
    - if: $CI_COMMIT_TAG
  script:
    - docker build -t "$CI_REGISTRY_IMAGE:$CI_COMMIT_TAG" .
    - echo "$CI_REGISTRY_PASSWORD" | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin
    - docker push "$CI_REGISTRY_IMAGE:$CI_COMMIT_TAG"
```

Pin CI tools according to repository policy, use secret stores and limit publication permissions. Supply integration databases as isolated services. Run Alembic against an empty database and exercise upgrade compatibility with representative old data. Preserve test and scan artifacts; a scan warning is not proof of a clean release.
