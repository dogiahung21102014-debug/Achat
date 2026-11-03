# Achat V2.1 — Security hardening (NOT production ready)

This release is an incremental security patch to V2, **not** a commercial SaaS release.

## Added
- CSRF tokens on HTML forms, server-side CSRF validation.
- Secure session cookie options for HTTPS production.
- Fail-fast when `APP_ENV=production` and SECRET_KEY / admin bootstrap credentials are weak or default.
- No demo shop/customer data automatically seeded when initializing a new production database.
- Basic security headers and proxy handling.

## Before commercial use (BLOCKERS)
1. Migrate SQLite to PostgreSQL with schema migrations, backups and restore drills.
2. Implement hardened multi-tenant authorization and automated cross-tenant access tests on **all** endpoints.
3. Add MFA for superadmins, login rate limits, password reset and session revocation.
4. Implement Facebook Login, Page permission review, webhooks, signature verification, token encryption and expiry handling.
5. Implement real carrier APIs with idempotent booking, retry, reconciliation, label printing and audit trails.
6. Build AI assistance with human confirmation, consent, conversation safety and measurable error rates.
7. Add monitoring, alerting, security review, privacy policy, terms and billing.
8. Replace in-process/SQLite demo persistence; don't deploy V2.1 as a paid product.

## Render upgrade notes
Set `APP_ENV=production`, `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` as environment variables. **Do not enable production mode against your existing demo database expecting it to remove demo accounts**: the demo accounts persist. To create a clean instance, provision a fresh database and use migrations; do not delete customer data from a live service.
