---
type: llm
---

PASS moves BaseSettings to pydantic-settings, replaces Config/orm_mode with
model_config and from_attributes, @validator with field_validator, parse_obj
with model_validate and dict with model_dump, checks installed FastAPI and
Pydantic versions first and requires request/response and settings tests.
FAIL if it upgrades unrelated packages or declares the migration complete from
imports or syntax alone.
