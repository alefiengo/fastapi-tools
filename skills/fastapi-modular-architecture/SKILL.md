---
name: fastapi-modular-architecture
description: Design and review module boundaries in a FastAPI application. Use for modular monoliths, import cycles or architecture checks.
---

# Modular Architecture for FastAPI

Inspect the current package layout and domain boundaries. Separate HTTP adapters, application behavior and persistence only when the codebase needs those boundaries. Use APIRouter composition and explicit dependency providers rather than global mutable registries.

Business modules should expose a small public API and avoid importing each other's private ORM models or sessions. Shared schemas and utilities need clear ownership. Build app factories when tests/configuration benefit; compose routers at the app boundary. Avoid importing the application instance from feature modules.

Check dependency direction with existing architecture tests or import-linter if
already configured. Otherwise inspect imports and propose a scoped check; do not
install or impose a new architecture tool. Python import cycles, re-exports and
runtime import hooks require inspection beyond static routes. Verify startup and
router registration with the actual app.

Deliver a boundary map, dependency direction, offending imports and a small migration plan. Preserve behavior with tests rather than creating layers for their own sake.
