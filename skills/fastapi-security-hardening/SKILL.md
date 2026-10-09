---
name: fastapi-security-hardening
description: Review and implement FastAPI authentication, authorization, JWT validation, cookies, CSRF and secret handling.
---

# Security Hardening for FastAPI

Inspect the existing auth mechanism and contract before changing it. For JWT, validate signature with an explicit allowed algorithm, issuer/audience when required, expiration and applicable claims. Reject invalid/expired tokens; never disable verification to make tests pass. Token extraction is not authentication.

Authorize object ownership/tenant access server-side on every relevant query. Derive identity from validated credentials; do not trust payload owner IDs. Test anonymous, invalid token, authorized and wrong-owner cases with the application's exact error contract. Avoid logging credentials or returning ORM secrets.

Cookie authentication needs a deliberate CSRF defense, Secure/HttpOnly/SameSite attributes and narrowly configured CORS origins with credentials. CORS alone does not prevent CSRF. A bearer-only API using an Authorization header has a different CSRF surface; mixed cookie/bearer flows need analysis of both.

Read secrets from environment or the existing secret store. pydantic-settings is separate from Pydantic v2. Use supported password hashing and auth packages already pinned in the project. Keep uploads, redirects and outbound URLs bounded and validated according to actual behavior.

Report demonstrated defects, fixes and validation, avoiding speculative security blockers.
