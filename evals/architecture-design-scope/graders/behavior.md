---
type: llm
---

PASS returns a design and an HTTP contract in the response that preserve the
sync Session and the simple router layout. It defines public response fields
(id and name only), authenticated ownership for mutations, the transaction
owner, the 404/403 convention and bounded deterministic pagination. FAIL if it
mandates new layers, an async ORM or extra tools, or claims executed checks.
