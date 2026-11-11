---
name: fastapi-pydantic-v1-to-v2-migration
description: Plan and implement a Pydantic v1 to v2 migration in a FastAPI project, including settings, validators and response compatibility.
---

# Pydantic V1 To V2 Migration for FastAPI

Discover the installed FastAPI, Pydantic, Starlette and HTTPX versions and lockfile constraints before proposing changes. Check official compatibility documentation; do not upgrade an unrelated dependency by default. Version boundaries: FastAPI 0.126.0 dropped Pydantic v1 and 0.128.0 dropped `pydantic.v1` models, so a gradual migration through `pydantic.v1` needs FastAPI 0.119–0.127 and Python 3.13 or older (`pydantic.v1` is unsupported on Python 3.14+). FastAPI 0.x minor releases also change request handling (for example 0.151.0 distinguishes JSON `null` from an omitted body value); read the "Breaking Changes" of every FastAPI release crossed.

Migrate incrementally with contract tests. `bump-pydantic` can automate routine rewrites; review its diff. Replace parse_obj with model_validate, parse_raw with model_validate_json, dict with model_dump, json with model_dump_json, copy with model_copy, update_forward_refs with model_rebuild, `__fields__` with model_fields and Field `regex` with `pattern` where appropriate; these substitutions still require checking serialization behavior. Use model_config/ConfigDict, from_attributes instead of orm_mode, field_validator/model_validator instead of legacy validators, and pydantic-settings for BaseSettings.

Review Optional fields: `str | None` accepts None but is required unless given a default. Audit coercion, aliases, Decimal/datetime JSON representation, custom types, validation error shape and schema generation. Never nest v1 and v2 models in each other: Pydantic does not support it in any version. Separate v1 and v2 models can coexist only inside the FastAPI/Python window above.

Test omitted, explicit null and invalid values separately. In v2, a TypeError
raised inside a validator is no longer converted into ValidationError; distinguish
a validator bug from rejected client input. For ORM responses, `from_attributes`
reads attributes and may trigger database I/O: eager-load required relationships
within the session rather than expecting Pydantic to await lazy loading.

Preserve public API behavior or document a deliberate breaking release. Run schema compatibility checks, request/response tests, settings tests and full verification after each stage. Do not claim migration complete from imports or syntax checking alone.

Reference: https://fastapi.tiangolo.com/how-to/migrate-from-pydantic-v1-to-pydantic-v2/
