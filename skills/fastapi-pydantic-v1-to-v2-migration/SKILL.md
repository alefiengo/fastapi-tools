---
name: fastapi-pydantic-v1-to-v2-migration
description: Plan and implement a Pydantic v1 to v2 migration in a FastAPI project, including settings, validators and response compatibility.
---

# Pydantic V1 To V2 Migration for FastAPI

Discover the installed FastAPI, Pydantic, Starlette and HTTPX versions and lockfile constraints before proposing changes. Check official compatibility documentation; do not upgrade an unrelated dependency by default.

Migrate incrementally with contract tests. Replace parse_obj with model_validate, dict with model_dump and json with model_dump_json where appropriate; these substitutions still require checking serialization behavior. Use model_config/ConfigDict, from_attributes instead of orm_mode, field_validator/model_validator instead of legacy validators, and pydantic-settings for BaseSettings.

Review Optional fields: `str | None` accepts None but is required unless given a default. Audit coercion, aliases, Decimal/datetime JSON representation, custom types, validation error shape and schema generation. Avoid mixing nested v1/v2 models without documented support for the installed versions.

Preserve public API behavior or document a deliberate breaking release. Run schema compatibility checks, request/response tests, settings tests and full verification after each stage. Do not claim migration complete from imports or syntax checking alone.

Reference: https://fastapi.tiangolo.com/how-to/migrate-from-pydantic-v1-to-pydantic-v2/
