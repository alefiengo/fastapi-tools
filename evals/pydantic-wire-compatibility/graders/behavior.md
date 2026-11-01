---
type: llm
---

PASS distinguishes nullable from omittable in v2, checks omitted/null/invalid
separately, preserves the stated Decimal wire contract, and recognizes validator
TypeError no longer becomes ValidationError. It requires loading ORM relationships
before response serialization; from_attributes does not await async lazy I/O.
FAIL for blind renaming as proof of compatibility, automatic dependency upgrades,
or claiming proposed tests have run.
