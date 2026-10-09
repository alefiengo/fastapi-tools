---
name: fastapi-contract-testing
description: Validate FastAPI provider/consumer contracts using OpenAPI, Schemathesis or the existing Pact workflow. Use for API compatibility and contract release tests.
---

# Contract Testing for FastAPI

Identify real consumers, the published contract version and the existing tooling. Test the wire contract, not just schema snapshots. Compare generated OpenAPI for path/method removals, required-field additions, narrowed accepted values, response changes and changed security requirements.

Use Schemathesis only if compatible with the project's installed version and authentication fixtures. Its generated cases supplement domain and ownership tests. Pact provider states must create deterministic isolated data and restore it. Never fake broker publication, verification or deployment approval.

For a release cycle: run consumer tests, produce the contract artifact, verify the provider with named states, publish evidence to the configured broker only when authorized, and run the broker's compatibility gate before deployment. A mocked service test does not establish compatibility with the actual deployed provider. Keep secrets out of contract artifacts.

Deliver exact commands supported by the installed tooling, contract provenance, changed operations and failures. Distinguish executed verification from a proposed workflow.
