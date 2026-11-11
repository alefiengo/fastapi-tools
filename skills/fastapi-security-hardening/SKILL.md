---
name: fastapi-security-hardening
description: Review and implement authentication, authorization, JWT validation, cookies, CSRF and secret handling in a FastAPI application. Not for Flask, Django or other frameworks.
---

# Security Hardening for FastAPI

Inspect the existing auth mechanism and contract before changing it. For JWT, validate signature with an explicit allowed algorithm, issuer/audience when required, expiration and applicable claims. Reject invalid/expired tokens; never disable verification to make tests pass. Token extraction is not authentication.

Authorize object ownership/tenant access server-side on every relevant query. Derive identity from validated credentials; do not trust payload owner IDs. Test anonymous, invalid token, authorized and wrong-owner cases with the application's exact error contract. Avoid logging credentials or returning ORM secrets.

Cookie authentication needs a deliberate CSRF defense, Secure/HttpOnly/SameSite attributes and narrowly configured CORS origins with credentials. CORS alone does not prevent CSRF. A bearer-only API using an Authorization header has a different CSRF surface; mixed cookie/bearer flows need analysis of both.

Read secrets from environment or the existing secret store. pydantic-settings is separate from Pydantic v2. Prefer auth packages already pinned in the project when they are maintained and work with the installed versions. For new code, FastAPI's OAuth2/JWT tutorial uses PyJWT (`jwt.decode(token, key, algorithms=[...], audience=..., issuer=...)`) and `pwdlib[argon2]` (`PasswordHash.recommended()`). passlib (last release 1.7.4, 2020) raises ValueError hashing and verifying with bcrypt 5; existing bcrypt hashes can be verified with `pwdlib[bcrypt]` and rehashed with Argon2 after a successful login. Keep uploads, redirects and outbound URLs bounded and validated according to actual behavior.

Report demonstrated defects, fixes and validation, avoiding speculative security blockers.
