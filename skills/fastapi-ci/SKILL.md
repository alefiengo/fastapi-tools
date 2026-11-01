---
name: fastapi-ci
description: Configure CI checks, dependency scanning and image publication for a FastAPI Python project. Use when asked to change FastAPI pipelines.
---

# Ci for FastAPI

Inspect repository scripts and supported Python versions. Preserve the existing package manager and lockfile. CI should install locked runtime and development dependencies, then run the same syntax/lint/type/test gates used locally. Missing test dependencies or no collected tests must fail. Publish packages or images only when explicitly requested.

For uv, synchronize with `uv sync --frozen --group dev` after inspecting declared groups. For a requirements project, use the repository's pinned requirements and separate development requirements. Do not invent a requirements-dev.txt that does not exist.

```yaml
# GitLab example for an existing uv project with a dev dependency group.
stages: [verify, publish]
verify:
  stage: verify
  image: python:3.12-slim
  script:
    - python -m pip install uv
    - uv sync --frozen --group dev
    - uv run --no-sync ruff check .
    - uv run --no-sync pytest --junitxml=reports/pytest.xml
  artifacts:
    when: always
    reports:
      junit: reports/pytest.xml
image-build:
  stage: publish
  image: docker:cli
  services: [docker:dind]
  rules:
    - if: $CI_COMMIT_TAG
  script:
    - docker build -t "$CI_REGISTRY_IMAGE:$CI_COMMIT_TAG" .
    - echo "$CI_REGISTRY_PASSWORD" | docker login "$CI_REGISTRY" -u "$CI_REGISTRY_USER" --password-stdin
    - docker push "$CI_REGISTRY_IMAGE:$CI_COMMIT_TAG"
```

Pin CI tools according to repository policy, use secret stores and limit publication permissions. Supply integration databases as isolated services. Run Alembic against an empty database and exercise upgrade compatibility with representative old data. Preserve test and scan artifacts; a scan warning is not proof of a clean release.
