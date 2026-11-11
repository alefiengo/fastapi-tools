---
description: Migrate Pydantic v1 models and settings in a FastAPI project.
max_turns: 10
allowed_tools: [Read, Glob, Grep, Skill, Agent]
---

Our FastAPI project still uses Pydantic v1: `class Settings(BaseSettings)` with
`class Config: env_file = ".env"`, response models with `orm_mode = True`,
`@validator("email")`, and `Order.parse_obj(payload)` plus `order.dict()` in
services. Plan the migration to Pydantic v2 without upgrading unrelated
dependencies, and say which tests must run before calling it complete.
