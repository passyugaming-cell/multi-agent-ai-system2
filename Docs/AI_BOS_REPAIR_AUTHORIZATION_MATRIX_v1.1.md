# AI BOS REPAIR AUTHORIZATION MATRIX v1.1

**Status:** AUTHORITATIVE AUDIT & AUTHORIZATION MATRIX
**Project:** AI Business Operating System (AI BOS)
**Baseline Commit:** `191e7553b480036f8908e5d2aee0f02a7ac193bf` on `ai-bos-repair-hardening`
**Purpose:** Revalidate all repository audit findings post R0-001 repair merge and establish definitive, evidence-backed repair authorization for subsequent phases.

---

# 1. EXECUTIVE SUMMARY

Task R0-001 (Phase 6 Integration Migration DDL Repair) has been successfully implemented, verified, and merged. All 5 Phase 6 integration tables (`integrations`, `integration_connections`, `integration_credentials`, `integration_executions`, `webhook_configs`) are authoritatively defined with foreign keys, unique constraints, and indexes. PostgreSQL 16 CI workflow `.github/workflows/r0_001_postgres_verification.yml` executes `alembic upgrade head`, schema inspection, pytest, and downgrade/upgrade round-trips cleanly.

This document reevaluates all historical findings R0 through R9 against current repository truth to determine what repair stream is authorized NEXT.

---

# 2. REPAIR AUTHORIZATION MATRIX v1.1

| ID | Priority | Finding Title | Current Status | Evidence Location | Authorization | Blocking Reason | Next Action |
|---|---|---|---|---|---|---|---|
| **R0-001** | P0 | Empty Phase 6 Integration Migration DDL | CLOSED / MERGED | `migrations/versions/2026_09_05_0857-5066dcbc0b43_add_phase6_integrations.py` | RESOLVED | None | Closed in R0-001. No further action needed. |
| **R1-001** | P0 | Tenant ID Is Not Authentication | UNRESOLVED | `app/api/v1/customers.py`, `orders.py`, `tasks.py`, `events.py` | AUTHORIZED_WITH_CONSTRAINTS | Requires route-by-route authorization resolution without breaking webhooks/public endpoints | Implement server-side actor verification across tenant API routes in R1. |
| **R1-002** | P0 | Unauthenticated Billing Mutation Paths | UNRESOLVED | `app/api/v1/billing.py` (`POST /subscription`, `/subscription/cancel`) | AUTHORIZED_WITH_CONSTRAINTS | Requires binding active actor identity to billing service calls | Enforce authenticated actor context and tenant permissions on billing routes. |
| **R1-003** | P0/P1 | Event/Workflow Security Escalation | UNRESOLVED | `app/core/workflows/actions.py`, `app/api/v1/events.py` | AUTHORIZED_WITH_CONSTRAINTS | `allow_internal` and `system_workflow` flags must not bypass tenant/risk boundaries | Enforce risk classifier and actor context on workflow actions. |
| **R1-004** | P1 | Minimum Privilege for System/Workflow Actors | UNRESOLVED | `app/core/auth.py`, `app/core/workflows/engine.py` | AUTHORIZED | Scope permissions strictly to required action domain | Restrict workflow actor permission sets in R1. |
| **R2-001** | P0 | Fake Payment Provider Production Fallback | UNRESOLVED | `app/billing/payments.py` (`PaymentService`) | BLOCKED_PENDING_DECISION | Fail-closed production configuration check required | Require explicit production payment provider configuration check. |
| **R2-002** | P0 | Default Payment Webhook Secret | UNRESOLVED | `app/core/config.py`, `app/billing/payments.py` | BLOCKED_PENDING_DECISION | Production config must reject default secret values | Enforce non-default webhook secret in production environment setup. |
| **R2-003** | P0/P1 | Dual Payment Webhook Authority | UNRESOLVED | `app/api/v1/billing.py` & `app/api/v1/webhooks.py` | BLOCKED_PENDING_DECISION | Two independent webhook endpoints exist (`/billing/webhooks/payment` & `/webhooks/midtrans`) | Owner decision required to consolidate canonical payment webhook route. |
| **R2-004** | P1 | Payment Amount & Invoice Reconciliation | UNRESOLVED | `app/billing/payments.py` | BLOCKED_PENDING_DECISION | Payment amounts not revalidated against invoice total on webhook receipt | Revalidate payment transaction amount against invoice total. |
| **R2-005** | P1 | Unified Payment State Machine | UNRESOLVED | `app/billing/state_machine.py` | BLOCKED_PENDING_DECISION | Provider states mapped ad-hoc without centralized state owner | Normalize provider payment states into unified state machine. |
| **R2-006** | P0/P1 | Subscription Activation Authority | UNRESOLVED | `app/billing/subscription.py` | BLOCKED_PENDING_DECISION | Subscription activation independent of verified payment | Bind entitlement activation strictly to verified payment transition. |
| **R2-007** | P1 | Entitlement Period Expiration | UNRESOLVED | `app/billing/entitlement.py` | BLOCKED_PENDING_DECISION | Expiration relies on background cron rather than runtime check | Enforce period expiry check dynamically at runtime. |
| **R2-008** | P1 | Refund Provider Model | UNRESOLVED | `app/billing/refunds.py` | BLOCKED_PENDING_DECISION | Refund model lacks provider refund ID tracking | Track provider refund transaction references in refund records. |
| **R3-001** | P1 | Outbound WhatsApp False Success | UNRESOLVED | `app/integrations/whatsapp/sender.py` | BLOCKED_PENDING_EVIDENCE | Webhook failure responses logged without marking message failed | Record explicit message execution state on outbound delivery failure. |
| **R3-002** | P1 | WhatsApp Message Idempotency | UNRESOLVED | `app/integrations/whatsapp/webhook.py` | BLOCKED_PENDING_EVIDENCE | Duplicate Meta webhook payloads create duplicate DB messages | Enforce idempotency key on external WhatsApp message ID. |
| **R3-003** | P1 | Webhook Parser Batch Processing | UNRESOLVED | `app/integrations/whatsapp/parser.py` | BLOCKED_PENDING_EVIDENCE | Multi-entry Meta webhook arrays parsed as single message | Iterate over multi-entry payload arrays in parser. |
| **R3-004** | P1 | Customer Response Ownership Race | UNRESOLVED | `app/core/router/router.py` | BLOCKED_PENDING_EVIDENCE | AI responds concurrently while human operator active | Enforce conversation ownership lock during human handoff. |
| **R3-005** | P1 | Phone Number Identity Normalization | UNRESOLVED | `app/repositories/domain.py` (`CustomerRepository`) | BLOCKED_PENDING_EVIDENCE | Non-E.164 phone formats create duplicate customer records | Normalize phone numbers to E.164 format before query/insert. |
| **R4-001** | P1 | Distributed AI Rate Limiter | UNRESOLVED | `app/core/ai_gateway/rate_limiter.py` | BLOCKED_PENDING_EVIDENCE | Rate limiter uses local in-memory dict instead of Redis across workers | Transition AI Gateway rate limiter to Redis backend. |
| **R4-002** | P1 | Atomic AI Usage Enforcement | UNRESOLVED | `app/core/ai_gateway/usage.py` | BLOCKED_PENDING_EVIDENCE | Usage check and increment non-atomic; DB error grants free usage | Enforce atomic usage reservation or fail-closed behavior. |
| **R4-003** | P1 | Primary AI Provider Failure Fallback | UNRESOLVED | `app/core/ai_gateway/gemini.py` | BLOCKED_PENDING_EVIDENCE | Gemini API timeout/error raises uncaught exception to caller | Implement graceful safe fallback message on provider failure. |
| **R4-004** | P1 | Runtime Guardrail Enforcement | UNRESOLVED | `app/database/models/guardrail.py` | BLOCKED_PENDING_EVIDENCE | Guardrail rules stored in DB but not evaluated during AI execution | Evaluate active guardrails in AIGateway before returning response. |
| **R4-005** | P1 | Deterministic-First Transactional Truth | UNRESOLVED | `app/core/router/deterministic.py` | BLOCKED_PENDING_EVIDENCE | AI reasoning allowed to estimate product price/stock | Revalidate price and stock from DB at transaction boundary. |
| **R5-001** | P1 | False-Success Workflow Actions | UNRESOLVED | `app/core/workflows/actions.py` | BLOCKED_PENDING_EVIDENCE | Actions return success status before verifying DB/provider result | Return success only after verified DB mutation. |
| **R5-002** | P1 | Event Handler Dead-Letter Queue | UNRESOLVED | `app/core/events/bus.py` | BLOCKED_PENDING_EVIDENCE | Failed event handlers acknowledge messages without DLQ retry | Route failed event executions to Dead-Letter Queue. |
| **R5-003** | P1 | Cross-Execution Workflow Loops | UNRESOLVED | `app/core/workflows/engine.py` | BLOCKED_PENDING_EVIDENCE | Event A triggering Workflow B triggering Event A causes infinite loop | Enforce correlation depth counter and cycle suppression. |
| **R5-004** | P1 | Integration Action Authorization | UNRESOLVED | `app/core/workflows/actions.py` | BLOCKED_PENDING_EVIDENCE | `call_agent` / integration actions bypass risk checks | Pass action through risk classifier and authority check. |
| **R6-001** | P1 | Cross-Tenant FK Integrity | UNRESOLVED | `app/database/models/` | BLOCKED_PENDING_EVIDENCE | Child records reference parent records without tenant matching | Verify tenant match on parent-child foreign key references. |
| **R6-002** | P1 | Client Memory Ownership Scoping | UNRESOLVED | `app/memory/client_memory.py` | BLOCKED_PENDING_EVIDENCE | Client memory scoped by key rather than customer UUID | Bind client memory records strictly to customer_id. |
| **R6-003** | P1 | Memory vs Authoritative DB Boundary | UNRESOLVED | `app/core/context_assembly/` | BLOCKED_PENDING_EVIDENCE | Stale memory facts override authoritative DB record | Enforce Source-of-Truth hierarchy (DB Facts > Memory). |
| **R7-001** | P1 | Business Plan Feature Alignment | UNRESOLVED | `app/billing/plans.py` | BLOCKED_PENDING_EVIDENCE | Business plan features conflict with Pro product scope | Align tenant plan features strictly with canonical blueprint. |
| **R7-002** | P1 | Service Onboarding Stock Requirement | UNRESOLVED | `app/tenants/onboarding_service.py` | BLOCKED_PENDING_EVIDENCE | Service onboarding forces physical stock input validation | Separate product stock validation from service items. |
| **R7-003** | P1 | Entitlement Enforcement Consistency | UNRESOLVED | `app/billing/entitlement.py` | BLOCKED_PENDING_EVIDENCE | Internal routes bypass plan feature entitlement checks | Enforce entitlement check across all API entrypoints. |
| **R8-001** | P1 | Dependency Declaration Reproducibility | UNRESOLVED | `pyproject.toml` | BLOCKED_PENDING_EVIDENCE | Test dependencies missing from main project dependencies | Declare all runtime/test dependencies in `pyproject.toml`. |
| **R8-002** | P1 | CI Workflow Branch Triggers | UNRESOLVED | `.github/workflows/main.yml` | BLOCKED_PENDING_EVIDENCE | Main CI workflow triggers manually on PR #33 branch | Configure `main.yml` for standard `push` and `pull_request` triggers. |
| **R9-001** | P2 | Backup / DR Restoration Evidence | UNRESOLVED | Infrastructure | BLOCKED_PENDING_EVIDENCE | No DR restoration procedure documented | Establish backup/restore procedure (P2). |
| **R9-002** | P2 | Data Retention & Deletion Policy | UNRESOLVED | Domain Services | BLOCKED_PENDING_EVIDENCE | No automated tenant data deletion/export pipeline | Implement tenant data export and purge pipeline (P2). |
| **R9-003** | P2 | Authentication Hardening (MFA/Brute Force) | UNRESOLVED | `app/api/v1/auth.py` | BLOCKED_PENDING_EVIDENCE | Login endpoint lacks IP brute-force rate limiting | Add rate limiting to `/auth/login` endpoint (P2). |
| **R9-004** | P2 | Frontend JWT Token Security | UNRESOLVED | `frontend/src/lib/api.ts` | BLOCKED_PENDING_EVIDENCE | JWT stored in browser localStorage | Transition to httpOnly secure cookie session handling (P2). |
| **R9-005** | P2 | Production Observability & Tracing | UNRESOLVED | App Core | BLOCKED_PENDING_EVIDENCE | OpenTelemetry tracing and structured metrics missing | Add OpenTelemetry tracing and Prometheus metrics (P2). |
| **R9-006** | P2 | Internal AI Role Exposure | UNRESOLVED | `app/agents/` | BLOCKED_PENDING_EVIDENCE | Specialist AI agent endpoints exposed without tenant plan gating | Restrict internal AI agent execution endpoints (P2). |

---

# 3. ROUTE INVENTORY & TRUST MODEL CLASSIFICATION

Every route in `app/api/v1/` is classified into one of six trust models:

1. **PUBLIC:** Open access (e.g., `/health`, `/auth/login`).
2. **AUTHENTICATED PLATFORM:** Requires Platform Owner authority (`is_platform_owner: True`).
3. **AUTHENTICATED TENANT:** Requires Bearer JWT token, active tenant context, and actor permissions.
4. **WEBHOOK:** Machine-to-machine provider payload verified via HMAC/signature or provider verification token.
5. **INTERNAL SYSTEM:** Internal workflow/event calls protected by server-side actor context.
6. **CUSTOMER-FACING:** Public customer interactions (e.g., product catalog queries) bound to active tenant context.

### Complete Route Inventory (`app/api/v1/`)

| Path | Method | Trust Model | Auth Dependency | Tenant Resolution | Permission Enforced |
|---|---|---|---|---|---|
| `/health` | GET | PUBLIC | None | None | None |
| `/health/db` | GET | PUBLIC | None | None | None |
| `/auth/login` | POST | PUBLIC | None | Client JSON Payload | None |
| `/auth/me` | GET | AUTHENTICATED TENANT | Bearer JWT | JWT `active_tenant_id` | None |
| `/auth/select-tenant` | POST | AUTHENTICATED TENANT | Bearer JWT | Client JSON `tenant_id` | Tenant Membership |
| `/auth/logout` | POST | AUTHENTICATED TENANT | Bearer JWT | JWT `active_tenant_id` | None |
| `/customers` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `customers:read` / `write` |
| `/customers/{customer_id}` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `customers:read` |
| `/orders` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `orders:read` / `write` |
| `/products` | GET, POST, PUT, DELETE | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `products:read` / `write` |
| `/products/variants/*` | POST, PUT, DELETE | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `products:write` |
| `/conversations` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `conversations:read` |
| `/conversations/{id}` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `conversations:read` |
| `/conversations/{id}/messages` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `conversations:read` / `write` |
| `/conversations/{id}/handoff` | POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `conversations:write` |
| `/business` | GET, PUT | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `business:read` / `write` |
| `/business/readiness` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `business:read` |
| `/business-profile` | GET, POST, PUT | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `business:read` / `write` |
| `/business-profile/readiness` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `business:read` |
| `/knowledge` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `knowledge:read` / `write` |
| `/knowledge/{id}` | GET, PUT, DELETE | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `knowledge:read` / `write` |
| `/knowledge/{id}/approve` | POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `knowledge:write` |
| `/knowledge/{id}/archive` | POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `knowledge:write` |
| `/integrations` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `VIEW_INTEGRATIONS` / `MANAGE_INTEGRATIONS` |
| `/integrations/connections` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `VIEW_INTEGRATIONS` / `MANAGE_INTEGRATIONS` |
| `/integrations/connections/{id}` | GET, DELETE | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `VIEW_INTEGRATIONS` / `MANAGE_INTEGRATIONS` |
| `/integrations/connections/{id}/credentials` | POST, GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `MANAGE_CREDENTIALS` |
| `/integrations/connections/{id}/execute` | POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `EXECUTE_INTEGRATION` |
| `/integrations/oauth/*` | GET, POST | AUTHENTICATED TENANT | HMAC signed state token | HMAC state `tenant_id` | `MANAGE_INTEGRATIONS` + `MANAGE_CREDENTIALS` |
| `/workflows` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `workflows:read` / `write` |
| `/workflows/{id}/*` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `workflows:read` / `write` |
| `/workflow-executions/*` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `workflows:read` / `write` |
| `/approvals` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `approvals:read` |
| `/approvals/{id}` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `approvals:read` |
| `/approvals/{id}/approve` | POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | Human Platform Owner or Requester Authority |
| `/approvals/{id}/reject` | POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | Human Requester / `business.write` / Platform Owner |
| `/approvals/{id}/cancel` | POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | Original Requester / `business.write` / Platform Owner |
| `/tasks` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `tasks:read` / `write` |
| `/tasks/{id}/*` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `tasks:write` |
| `/events` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `events:read` / `write` |
| `/analytics/*` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `analytics:read` |
| `/analytics/owner/platform` | GET | AUTHENTICATED PLATFORM | Bearer JWT | Server Actor `is_platform_owner` | `is_platform_owner == True` |
| `/owner-ai/*` | GET, POST | AUTHENTICATED PLATFORM | Bearer JWT | Server Actor `is_platform_owner` | `is_platform_owner == True` |
| `/agents/*` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | Agent Entitlement Check |
| `/billing/plans` | GET | PUBLIC / TENANT | None / JWT | Optional Context | None |
| `/billing/subscription` | GET, POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `billing:read` / `write` |
| `/billing/subscription/*` | POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `billing:write` |
| `/billing/usage` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `billing:read` |
| `/billing/invoices` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `billing:read` |
| `/billing/payments` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `billing:read` |
| `/billing/payments/{id}/refund` | POST | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `billing:write` + Risk Classifier |
| `/billing/entitlements` | GET | AUTHENTICATED TENANT | Bearer JWT | `X-Tenant-ID` / Context | `billing:read` |
| `/billing/webhooks/payment` | POST | WEBHOOK | Provider Signature | Account/Invoice Mapping | Signature Verification |
| `/webhooks/midtrans` | POST | WEBHOOK | Signature Key | Order/Invoice Mapping | Signature Verification |
| `/webhooks/whatsapp` | GET, POST | WEBHOOK | Verification Token / Signature | Phone Number Account Mapping | `X-Hub-Signature-256` |
| `/webhooks/inbound/{provider}` | POST | WEBHOOK | Provider HMAC Signature | Connection Account Mapping | Provider HMAC Check |
| `/tenants/provision` | POST | AUTHENTICATED PLATFORM | Bearer JWT | New Tenant UUID | `is_platform_owner == True` |
| `/tenants/{id}/onboarding/*` | GET, POST, PATCH | AUTHENTICATED TENANT | Bearer JWT | `{tenant_id}` Path Param | `onboarding:read` / `write` |
| `/tenants/{id}/lifecycle/transition` | POST | AUTHENTICATED TENANT | Bearer JWT | `{tenant_id}` Path Param | `onboarding:write` |

---

# 4. WEBHOOK TRUST MODEL ANALYSIS

Provider webhooks represent machine-to-machine integration traffic and MUST NOT require human user Bearer JWT tokens. Each webhook route enforces specialized cryptographic and account-mapping controls:

1. **Midtrans Webhook (`/webhooks/midtrans` & `/billing/webhooks/payment`):**
   - **Verification:** SHA-512 signature key comparison (`SHA512(order_id + status_code + gross_amount + ServerKey)`).
   - **Tenant Resolution:** Derived strictly from DB lookup on `order_id` / `invoice_id`.
   - **Gaps:** Dual routes exist (`/billing/webhooks/payment` and `/webhooks/midtrans`). Payment amount is not revalidated against invoice total prior to marking paid.

2. **WhatsApp Cloud API Webhook (`/webhooks/whatsapp`):**
   - **Verification:** `GET` handles challenge verification token; `POST` enforces mandatory `X-Hub-Signature-256` HMAC validation against `WHATSAPP_APP_SECRET`. Unsigned webhooks reject with HTTP 401.
   - **Tenant Resolution:** Derived strictly from DB lookup on `display_phone_number_id` against active `IntegrationConnection` records.
   - **Gaps:** Batch Meta webhook payloads with multiple entries are not iteratively parsed.

3. **Inbound Integration Webhooks (`/webhooks/inbound/{provider}`):**
   - **Verification:** HMAC signature verification against stored encrypted secret in `WebhookConfig`.
   - **Tenant Resolution:** Derived strictly from `WebhookConfig.tenant_id`.

---

# 5. P0 / P1 GATING & DEPENDENCY ORDER

## P0 GATE

| ID | Title | Status | Repaired? | Independent Verification | Authorized? |
|---|---|---|---|---|---|
| **R0-001** | Phase 6 Integration Migration Repair | MERGED | YES | PASS (PostgreSQL 16 CI workflow `.github/workflows/r0_001_postgres_verification.yml`) | CLOSED |
| **R1-001** | Tenant ID Is Not Authentication | UNRESOLVED | NO | NO | **AUTHORIZED_WITH_CONSTRAINTS** |
| **R1-002** | Billing Mutation Authorization | UNRESOLVED | NO | NO | **AUTHORIZED_WITH_CONSTRAINTS** |
| **R1-003** | Event/Workflow Security Chain | UNRESOLVED | NO | NO | **AUTHORIZED_WITH_CONSTRAINTS** |
| **R2-001** | Fake Payment Provider Production Fallback | UNRESOLVED | NO | NO | **BLOCKED_PENDING_DECISION** |
| **R2-002** | Default Webhook Secret | UNRESOLVED | NO | NO | **BLOCKED_PENDING_DECISION** |
| **R2-003** | Dual Payment Webhook Authority | UNRESOLVED | NO | NO | **BLOCKED_PENDING_DECISION** |

**P0 Gate Status:** **NO-GO** (Unresolved P0 security & authorization issues remain in R1 and R2).

---

## P1 GATE

| ID | Title | Status | Repaired? | Independent Verification | Authorized? |
|---|---|---|---|---|---|
| **R1-004** | Minimum Privilege for System/Workflow Actors | UNRESOLVED | NO | NO | **AUTHORIZED** |
| **R2-004** | Payment Amount & Invoice Reconciliation | UNRESOLVED | NO | NO | **BLOCKED_PENDING_DECISION** |
| **R2-005** | Unified Payment State Machine | UNRESOLVED | NO | NO | **BLOCKED_PENDING_DECISION** |
| **R2-006** | Subscription Activation Authority | UNRESOLVED | NO | NO | **BLOCKED_PENDING_DECISION** |
| **R2-007** | Entitlement Period Expiration | UNRESOLVED | NO | NO | **BLOCKED_PENDING_DECISION** |
| **R2-008** | Refund Provider Model | UNRESOLVED | NO | NO | **BLOCKED_PENDING_DECISION** |
| **R3-001** | Outbound WhatsApp False Success | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R3-002** | WhatsApp Message Idempotency | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R3-003** | Webhook Parser Batch Processing | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R3-004** | Customer Response Ownership Race | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R3-005** | Phone Number Identity Normalization | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R4-001** | Distributed AI Rate Limiter | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R4-002** | Atomic AI Usage Enforcement | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R4-003** | Primary AI Provider Failure Fallback | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R4-004** | Runtime Guardrail Enforcement | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R4-005** | Deterministic-First Transactional Truth | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R5-001** | False-Success Workflow Handlers | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R5-002** | Event Handler Dead-Letter Queue | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R5-003** | Cross-Execution Workflow Loops | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R5-004** | Integration Action Authorization | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R6-001** | Cross-Tenant FK Integrity | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R6-002** | Client Memory Ownership Scoping | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R6-003** | Memory vs Authoritative DB Boundary | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R7-001** | Business Plan Feature Alignment | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R7-002** | Service Onboarding Stock Requirement | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R7-003** | Entitlement Enforcement Consistency | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R8-001** | Dependency Declaration Reproducibility | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |
| **R8-002** | CI Workflow Branch Triggers | UNRESOLVED | NO | NO | **BLOCKED_PENDING_EVIDENCE** |

**P1 Gate Status:** **NO-GO**

---

## DEPENDENCY WORKFLOW ORDER

To preserve security boundaries and prevent regression cascading, repairs must proceed strictly in this sequence:

1. **R0 — Repository & Migration Integrity** *(CLOSED/PASS)*
2. **R1 — Security & Tenant Authorization Boundary** *(NOW AUTHORIZED FOR IMPLEMENTATION)*
3. **R2 — Payment & Billing Authority & Integrity**
4. **R3 — WhatsApp End-to-End Reliability**
5. **R4 — AI Gateway & AI Runtime Safety**
6. **R5 — Workflow, Event & Action Integrity**
7. **R6 — Data Integrity, Identity & Memory Scoping**
8. **R7 — Entitlement, Plan & Product Alignment**
9. **R8 — CI/CD & Dependency Reproducibility**
10. **R9 — Production Hardening (P2)**

---

# 6. NEXT REPAIR AUTHORIZATION

**First Authorized Repair Task:** **R1 — Security & Tenant Authorization Boundary**

### Justification & Constraints
With R0-001 completely closed and verified on main, the system security foundation must be established prior to payment or workflow repairs. R1 is authorized with the following strict constraints:
1. Enforce server-side authenticated actor context (`get_actor_context()`) across all tenant API routes in `app/api/v1/`.
2. Reject requests where client header `X-Tenant-ID` does not match the authenticated actor's tenant membership.
3. Preserve M2M webhook trust models (Midtrans, WhatsApp, Inbound Webhooks) without requiring user JWT tokens.
4. Restrict `allow_internal` and `system_workflow` flags from bypassing risk classification or tenant boundaries.

---

# FINAL AUDIT POSITION

```text
R0-001:
CLOSED / PASS

Overall Build Readiness:
NO-GO

Production Readiness:
NO-GO

Unresolved P0:
6 (R1-001, R1-002, R1-003, R2-001, R2-002, R2-003)

Unresolved P1:
28

Blocked Decisions:
[R2-003: Dual Payment Webhook Authority Consolidation]

First Authorized Repair:
R1 — Security & Tenant Authorization Boundary

Reason:
R0-001 is merged and verified. Server-side actor authentication and tenant boundary enforcement across domain endpoints (R1) is the essential security prerequisite before addressing billing, WhatsApp, and workflow execution engines.

Next Required Action:
Await Project Owner authorization to begin R1 implementation on a dedicated branch (`feature/ai-bos-repair-r1-security`).
```
