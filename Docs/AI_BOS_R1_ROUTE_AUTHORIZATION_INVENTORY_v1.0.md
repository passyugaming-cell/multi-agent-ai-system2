# AI BOS R1 ROUTE AUTHORIZATION INVENTORY v1.0

**Status:** AUTHORITATIVE ROUTE CLASSIFICATION & SECURITY INVENTORY
**Branch:** `ai-bos-r1-security-hardening`
**Purpose:** Classify every API endpoint in `app/api/v1/` into its explicit trust model and define required R1 security controls.

---

# 1. TRUST MODEL CLASSIFICATIONS

Every API endpoint is classified into one of six explicit trust models:

1. **PUBLIC:** Open access endpoints (e.g., `/health`, `/auth/login`). No JWT or tenant required.
2. **AUTHENTICATED PLATFORM:** Requires Platform Owner authority (`actor.is_platform_owner == True`). Rejects all non-platform owners (including tenant owners) with HTTP 403.
3. **AUTHENTICATED TENANT:** Requires Bearer JWT token, active server-derived tenant context (`actor.tenant_id == request_tenant_id`), and required actor permissions resolved via `resolve_actor_permissions`. Unauthenticated or cross-tenant calls fail with HTTP 401 / 403.
4. **WEBHOOK:** Machine-to-machine provider webhooks verified via HMAC signatures (`X-Hub-Signature-256`, Midtrans SHA-512 key) or verification tokens. Does not require user JWT tokens.
5. **INTERNAL SYSTEM:** Internal workflow/event calls protected by trusted server-side system actor context (`get_actor_context()`). Rejects unauthenticated external requests.
6. **CUSTOMER-FACING:** Public customer interactions (e.g., public catalog queries) bound to active tenant context without granting tenant admin capabilities.

---

# 2. COMPLETE ROUTE INVENTORY (`app/api/v1/`)

| File | Endpoint Path | Method | Trust Model | Auth Mechanism | Tenant Source | Permission Required | Required R1 Security Control |
|---|---|---|---|---|---|---|---|
| `health.py` | `/health` | GET | PUBLIC | None | None | None | Public health check. |
| `health.py` | `/health/db` | GET | PUBLIC | None | None | None | Public DB readiness check. |
| `auth.py` | `/auth/login` | POST | PUBLIC | Credentials | Client JSON | None | Verify user credentials; issue JWT containing `jti`, `user_id`, `tenant_ids`. |
| `auth.py` | `/auth/me` | GET | AUTHENTICATED TENANT | Bearer JWT | JWT `active_tenant_id` | None | Verify active token in DB; populate `AuthenticatedActor`. |
| `auth.py` | `/auth/select-tenant` | POST | AUTHENTICATED TENANT | Bearer JWT | Client JSON `tenant_id` | Tenant Membership | Verify user belongs to target tenant; issue updated JWT token. |
| `auth.py` | `/auth/logout` | POST | AUTHENTICATED TENANT | Bearer JWT | JWT `active_tenant_id` | None | Revoke JWT token JTI on server side. |
| `customers.py` | `/customers` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `customers:read` / `write` | Require `actor_perms: set[str] = Depends(resolve_actor_permissions)`. |
| `customers.py` | `/customers/{customer_id}` | GET | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `customers:read` | Require `actor_perms` and verify customer belongs to active tenant. |
| `orders.py` | `/orders` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `orders:read` / `write` | Require `actor_perms` and enforce active tenant scope. |
| `products.py` | `/products` | GET, POST, PUT, DELETE | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `products:read` / `write` | Require `actor_perms` and reject cross-tenant access. |
| `products.py` | `/products/variants/*` | POST, PUT, DELETE | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `products:write` | Require `actor_perms` and verify variant product tenant match. |
| `conversations.py` | `/conversations` | GET | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `conversations:read` | Require `actor_perms` and filter by active tenant context. |
| `conversations.py` | `/conversations/{id}` | GET | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `conversations:read` | Require `actor_perms` and verify conversation tenant match. |
| `conversations.py` | `/conversations/{id}/messages` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `conversations:read` / `write` | Require `actor_perms` and verify conversation tenant match. |
| `conversations.py` | `/conversations/{id}/handoff` | POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `conversations:write` | Require `actor_perms` and set human handoff state. |
| `business.py` | `/business` | GET, PUT | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `business:read` / `write` | Require `actor_perms` and update tenant business profile. |
| `business.py` | `/business/readiness` | GET | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `business:read` | Require `actor_perms` and compute onboarding score. |
| `business_profile.py` | `/business-profile` | GET, POST, PUT | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `business:read` / `write` | Require `actor_perms` and enforce active tenant context. |
| `business_profile.py` | `/business-profile/readiness` | GET | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `business:read` | Require `actor_perms` and compute readiness score. |
| `knowledge.py` | `/knowledge` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `knowledge:read` / `write` | Require `actor_perms` and enforce active tenant context. |
| `knowledge.py` | `/knowledge/{id}` | GET, PUT, DELETE | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `knowledge:read` / `write` | Require `actor_perms` and verify item tenant match. |
| `knowledge.py` | `/knowledge/{id}/approve` | POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `knowledge:write` | Require `actor_perms` and set item status to approved. |
| `knowledge.py` | `/knowledge/{id}/archive` | POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `knowledge:write` | Require `actor_perms` and archive knowledge item. |
| `integrations.py` | `/integrations` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `VIEW_INTEGRATIONS` / `MANAGE_INTEGRATIONS` | Require `_resolve_permissions_server` and enforce tenant context. |
| `integrations.py` | `/integrations/connections` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `VIEW_INTEGRATIONS` / `MANAGE_INTEGRATIONS` | Require `_resolve_permissions_server` and enforce tenant context. |
| `integrations.py` | `/integrations/connections/{id}` | GET, DELETE | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `VIEW_INTEGRATIONS` / `MANAGE_INTEGRATIONS` | Require `_resolve_permissions_server` and reject cross-tenant IDs. |
| `integrations.py` | `/integrations/connections/{id}/credentials` | POST, GET | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `MANAGE_CREDENTIALS` | Require `_resolve_permissions_server` and redact secrets. |
| `integrations.py` | `/integrations/connections/{id}/execute` | POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `EXECUTE_INTEGRATION` | Require `_resolve_permissions_server` and evaluate risk classifier. |
| `integrations.py` | `/integrations/oauth/*` | GET, POST | AUTHENTICATED TENANT | HMAC signed state | HMAC state `tenant_id` | `MANAGE_INTEGRATIONS` + `MANAGE_CREDENTIALS` | Verify HMAC state token, user_id match, and server permissions. |
| `workflows.py` | `/workflows` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `workflows:read` / `write` | Require `actor_perms` and enforce active tenant scope. |
| `workflows.py` | `/workflows/{id}/*` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `workflows:read` / `write` | Require `actor_perms` and verify workflow tenant match. |
| `workflow_executions.py` | `/workflow-executions/*` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `workflows:read` / `write` | Require `actor_perms` and verify execution tenant match. |
| `approvals.py` | `/approvals` | GET, GET /{id} | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `approvals:read` | Require `resolve_actor_permissions` and filter by tenant. |
| `approvals.py` | `/approvals/{id}/approve` | POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | Requester / Platform Owner Authority | Block self-approval by AI agents; enforce approver identity binding. |
| `approvals.py` | `/approvals/{id}/reject` | POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | Requester / `business.write` / Platform Owner | Enforce server-derived actor identity; reject cross-tenant calls. |
| `approvals.py` | `/approvals/{id}/cancel` | POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | Original Requester / `business.write` / Platform Owner | Enforce pending status and requester identity check. |
| `tasks.py` | `/tasks` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `tasks:read` / `write` | Require `actor_perms` and enforce active tenant scope. |
| `tasks.py` | `/tasks/{id}/*` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `tasks:write` | Require `actor_perms` and verify task tenant match. |
| `events.py` | `/events` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `events:read` / `write` | Require `actor_perms`; reject unauthenticated event injection. |
| `analytics.py` | `/analytics/*` | GET | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `analytics:read` | Require `actor_perms` and compute tenant-scoped analytics metrics. |
| `analytics.py` | `/analytics/owner/platform` | GET | AUTHENTICATED PLATFORM | Bearer JWT | Server Actor `is_platform_owner` | `is_platform_owner == True` | Enforce platform owner authority check; reject tenant owners. |
| `owner_ai.py` | `/owner-ai/*` | GET, POST | AUTHENTICATED PLATFORM | Bearer JWT | Server Actor `is_platform_owner` | `is_platform_owner == True` | Enforce server-derived `enforce_owner_actor`; reject tenant calls. |
| `agents.py` | `/agents/*` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | Specialist Agent Entitlement | Require `actor_perms`; block non-platform owners executing `owner_ai`. |
| `billing.py` | `/billing/plans` | GET, GET /{id} | PUBLIC / TENANT | None / JWT | Optional Context | None | Public plan catalog discovery. |
| `billing.py` | `/billing/subscription` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `billing:read` / `write` | Require `actor_perms`; bind active actor identity to subscription calls. |
| `billing.py` | `/billing/subscription/*` | POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `billing:write` | Require `actor_perms`; bind active actor identity to plan change/cancel. |
| `billing.py` | `/billing/usage` | GET, GET /{metric} | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `billing:read` | Require `actor_perms` and query tenant usage records. |
| `billing.py` | `/billing/invoices` | GET, GET /{id} | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `billing:read` | Require `actor_perms` and query tenant invoice records. |
| `billing.py` | `/billing/payments` | GET, GET /{id} | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `billing:read` | Require `actor_perms` and query tenant payment records. |
| `billing.py` | `/billing/payments/{id}/refund` | POST | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `billing:write` | Require `actor_perms` and evaluate risk classifier. |
| `billing.py` | `/billing/entitlements` | GET | AUTHENTICATED TENANT | Bearer JWT | Server Actor / ContextVar | `billing:read` | Require `actor_perms` and query active tenant entitlements. |
| `billing.py` | `/billing/webhooks/payment` | POST | WEBHOOK | Provider Signature | Account/Invoice Mapping | Signature Verification | Verify SHA-512 signature key; derive tenant from invoice/order. |
| `webhooks.py` | `/webhooks/midtrans` | POST | WEBHOOK | Signature Key | Order/Invoice Mapping | Signature Verification | Verify SHA-512 signature key; derive tenant from order. |
| `webhooks.py` | `/webhooks/whatsapp` | GET, POST | WEBHOOK | Verification Token / Signature | Phone Account Mapping | `X-Hub-Signature-256` | Verify `X-Hub-Signature-256` HMAC; derive tenant from phone ID. |
| `webhooks.py` | `/webhooks/inbound/{provider}` | POST | WEBHOOK | Provider HMAC Signature | WebhookConfig Mapping | Provider HMAC Check | Verify HMAC signature against `WebhookConfig.encrypted_secret`. |
| `onboarding.py` | `/tenants/provision` | POST | AUTHENTICATED PLATFORM | Bearer JWT | New Tenant UUID | `is_platform_owner == True` | Enforce platform owner authority check. |
| `onboarding.py` | `/tenants/{id}/onboarding/*` | GET, POST, PATCH | AUTHENTICATED TENANT | Bearer JWT | `{tenant_id}` Path Param | `onboarding:read` / `write` | Require `resolve_actor_permissions` and match `{tenant_id}` with actor. |
| `onboarding.py` | `/tenants/{id}/lifecycle/transition` | POST | AUTHENTICATED TENANT | Bearer JWT | `{tenant_id}` Path Param | `onboarding:write` | Require `resolve_actor_permissions` and match `{tenant_id}` with actor. |
