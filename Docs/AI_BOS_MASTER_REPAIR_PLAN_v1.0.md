# AI BOS MASTER REPAIR PLAN v1.0

**Status:** REPAIR SPECIFICATION — READY FOR IMPLEMENTATION  
**Project:** AI Business Operating System (AI BOS)  
**Purpose:** Repair and harden the existing repository after the completed repository-level audit.  
**Important:** This document is NOT a redesign of AI BOS. It is a controlled repair plan for the existing implementation.

---

# 1. DOCUMENT CONTROL

## 1.1 Authority

This Repair Plan operates under:

1. `MASTER_BLUEPRINT_FINAL_v1.1.md` — canonical product/architecture direction.
2. Locked decisions `Q1 → Q51` — parent decision baseline.
3. `MASTER_EXECUTION_PLAN_FINAL_v1.1.md` — implementation, testing, safety and PR protocol.
4. The latest repository audit findings and CI evidence.
5. This document — actionable repair specification derived from those findings.

The repository is the implementation subject.

## 1.2 Non-negotiable rule

**REPAIR, DO NOT REBUILD.**

The executor must preserve the existing AI BOS architecture and Universal Core unless an audited finding proves a specific implementation change is required.

Do not:
- redesign the product;
- replace the architecture wholesale;
- create duplicate subsystems;
- silently change Q1–Q51;
- turn future features into MVP/Pro features merely because they are convenient;
- remove safety controls to make tests pass;
- bypass authorization, entitlement, tenant isolation, AIGateway, approvals, or deterministic business rules;
- merge directly to `main`.

## 1.3 Source integrity

Historical findings must be revalidated against the current repository before modification.

For each finding:

`Finding → Current repository evidence → Still exists? → Repair / Mark resolved`

Do not blindly apply an old finding if the code has changed.

---

# 2. AUDIT CONTROL CENTER

| Item | Current status |
|---|---|
| Current stage | REPAIR & HARDENING |
| Previous stage | Repository Full Audit |
| Audit result | NO-GO |
| Current build status | NOT READY |
| Current production status | NOT SAFE |
| Coding allowed | YES, ONLY FOR REPAIR ITEMS IN THIS PLAN |
| Product redesign allowed | NO |
| Q1–Q51 changes | NO |
| Main branch modification | NO |
| Main merge | NO |
| Final authority | Project Owner |
| Implementation executor | Jules / GitHub Copilot |
| Independent reviewer | ChatGPT / independent audit |
| Exit condition | All applicable P0/P1 repaired + evidence + regression + independent PASS |

---

# 3. REPAIR PRIORITY MODEL

## P0 — Build / Security / Financial Blocker

Must be resolved before dependent implementation proceeds.

Examples:
- broken fresh-database migration;
- unauthenticated billing mutation;
- production billing using fake provider;
- security boundary that allows tenant operations without authenticated actor;
- financial authority bypass.

## P1 — Critical Reliability / Integrity / Runtime Safety

Must be resolved before production and before declaring the system build-ready.

Examples:
- false-success workflow actions;
- ineffective distributed rate limiting;
- non-atomic AI usage enforcement;
- missing provider failure strategy;
- duplicate WhatsApp messages;
- weak identity/state handling;
- event loss;
- workflow loops;
- guardrails stored but not enforced.

## P2 — Hardening / Production Maturity

Can follow after P0/P1 unless a dependency makes it earlier.

Examples:
- DR/restore evidence;
- retention/deletion/export;
- MFA/brute-force hardening;
- frontend token storage;
- full observability;
- implementation alignment for internal AI roles.

---

# 4. REPAIR WORKSTREAM ORDER

Execute in this dependency order:

1. **R0 — Repository/Migration Integrity**
2. **R1 — Security & Tenant Authorization Boundary**
3. **R2 — Payment/Billing Authority & Integrity**
4. **R3 — WhatsApp End-to-End Reliability**
5. **R4 — AI Gateway / AI Runtime Safety**
6. **R5 — Workflow / Event / Action Integrity**
7. **R6 — Data Integrity / Identity / Memory / Tenant FK**
8. **R7 — Entitlement / Plan / Product Alignment**
9. **R8 — CI/CD / Dependency Reproducibility**
10. **R9 — P2 Production Hardening**
11. **R10 — Targeted Re-audit**
12. **R11 — Full Regression**
13. **R12 — Independent Final Audit**

A later workstream must not be used to conceal an earlier unresolved P0/P1.

---

# 5. R0 — REPOSITORY & MIGRATION INTEGRITY

## R0-001 — Main migration blocker

**Priority:** P0  
**Finding:** `alembic/versions/5066dcbc0b43_add_phase6_integrations.py` contains empty `upgrade()` / `downgrade()` while later migrations require integration tables.

### Required repair

- Revalidate current migration chain.
- Ensure required Phase 6 integration DDL exists in the correct migration.
- Ensure migration ordering is deterministic.
- Ensure downgrade behavior is safe and consistent.
- Do not create duplicate tables if another migration already owns them.
- Validate from a clean PostgreSQL database.

### Acceptance

- Fresh database can migrate from base to head.
- Existing database can upgrade safely.
- Schema validation passes.
- Integration tables/constraints exist exactly once.
- Relevant migration tests pass.
- No destructive migration is introduced without explicit authorization.

---

# 6. R1 — SECURITY & TENANT AUTHORIZATION

## R1-001 — Tenant ID is not authentication

**Priority:** P0

### Finding

Tenant context can be supplied while actor authentication/authorization is not consistently required across tenant-scoped endpoints.

Affected examples include:
- customers;
- conversations;
- orders;
- tasks;
- events;
- workflows;
- workflow executions;
- analytics;
- onboarding;
- billing.

### Required repair

For every tenant-scoped API:

`Request → Authentication → Actor → Tenant membership/scope → Permission → Handler`

Do not permit:

`Request → X-Tenant-ID → Handler`

unless the endpoint is explicitly public and intentionally designed as such.

### Acceptance

Create a route inventory and classify every endpoint:

- PUBLIC
- AUTHENTICATED PLATFORM
- AUTHENTICATED TENANT
- INTERNAL SYSTEM
- WEBHOOK
- CUSTOMER-FACING

Every tenant route has explicit authentication and authorization.

Negative tests must prove:
- no JWT → denied;
- invalid JWT → denied;
- valid actor in tenant A requesting tenant B → denied;
- insufficient permission → denied;
- suspended/archived tenant → denied where policy requires;
- valid actor + valid tenant + permission → allowed.

---

## R1-002 — Billing mutation authorization

**Priority:** P0

### Affected operations

- subscription activation;
- plan change;
- cancellation;
- refund;
- other billing mutations.

### Required repair

Every mutation must pass:
- authenticated actor;
- tenant scope;
- permission;
- entitlement/business rule;
- state preconditions;
- idempotency where applicable;
- audit record.

No billing mutation may be authorized merely by knowing a tenant ID.

### Acceptance

Unauthorized and cross-tenant mutation tests fail closed.

---

## R1-003 — Workflow/event security chain

**Priority:** P0/P1

### Finding

Unauthenticated tenant event injection can potentially reach workflow execution paths with broad `system_workflow` permissions.

### Required repair

Define explicit authority for:
- external event;
- internal event;
- webhook event;
- workflow trigger;
- workflow executor;
- system actor.

External event data is data, not authority.

`allow_internal=True` must NOT bypass:
- tenant isolation;
- permission;
- entitlement;
- risk;
- approval;
- policy;
- action validation.

### Acceptance

Attempt:

`unauthenticated request → tenant event → workflow → privileged action`

must fail at the appropriate boundary.

---

## R1-004 — Minimum privilege for workflow/system actors

**Priority:** P1

Remove broad permissions that are not required by a specific workflow action.

Workflow actor permissions must be:
- explicit;
- action-scoped;
- tenant-scoped;
- risk-aware;
- auditable.

---

# 7. R2 — PAYMENT / BILLING AUTHORITY & INTEGRITY

## R2-001 — Fake payment provider default

**Priority:** P0

### Finding

`PaymentService` can default to `FakePaymentProvider`.

### Required repair

Production configuration must fail closed if a real provider is not configured.

Fake provider may exist only for:
- tests;
- explicit local development;
- isolated simulation.

It must never silently become production payment authority.

### Acceptance

Production-like startup/configuration without real provider:
- fails readiness, or
- blocks payment operations.

Tests explicitly inject fake provider.

---

## R2-002 — Default webhook secret

**Priority:** P0

### Finding

Payment webhook secret defaults to a test value.

### Required repair

- Remove insecure production fallback.
- Require configured secret for production.
- Validate signature before processing.
- Keep secret out of logs, memory/knowledge, AI context and error responses.

### Acceptance

Missing production secret → readiness failure or webhook disabled.

Invalid signature → denied.

Valid signature → processed.

---

## R2-003 — Dual payment webhook authority

**Priority:** P0/P1

### Finding

Two payment webhook processing paths exist:
- `/billing/webhooks/payment`
- `/webhooks/midtrans`

### Required repair

Choose and document one canonical payment-state authority.

If compatibility routes must remain:
- one must delegate to the canonical processor;
- no duplicate state transitions;
- common idempotency;
- common reconciliation;
- common audit.

Do not allow two independent authorities.

### Acceptance

A provider event delivered through any supported route produces one logical state transition.

---

## R2-004 — Payment amount reconciliation

**Priority:** P1

Before accepting a payment as authoritative:
- identify tenant/invoice/order;
- validate provider payment ID;
- validate expected amount/currency where applicable;
- validate transaction mapping;
- validate state transition;
- prevent replay.

### Acceptance

Wrong amount / wrong tenant / wrong invoice / replayed event cannot create a false PAID state.

---

## R2-005 — Unified payment state machine

**Priority:** P1

Normalize provider-specific states into the AI BOS payment model.

Provider states must not directly become arbitrary internal states without mapping.

Required:
- explicit state owner;
- valid transitions;
- idempotency;
- UNKNOWN handling;
- audit.

---

## R2-006 — Subscription activation authority

**Priority:** P0/P1

Activation must not be possible independently of verified payment when payment is required by the business contract.

Define:

`Payment verification → billing state → entitlement activation`

No duplicate activation authority.

---

## R2-007 — Entitlement expiration

**Priority:** P1

Resolver must enforce current subscription period state at runtime.

Do not rely only on scheduled expiration jobs.

Acceptance:
- expired period cannot retain paid entitlements;
- reconciliation is idempotent;
- downgrade/cancellation does not silently delete tenant data.

---

## R2-008 — Refund model

**Priority:** P1

Support provider refund identity and state safely enough for the current product scope.

At minimum:
- provider refund ID;
- original payment reference;
- amount;
- status;
- timestamps;
- idempotency;
- audit.

Do not claim advanced partial/multi-refund support unless implemented and tested.

---

# 8. R3 — WHATSAPP END-TO-END RELIABILITY

## R3-001 — Outbound false success

**Priority:** P1

### Finding

Some outbound failure paths can still record/send success-like state or publish `whatsapp.message_sent`.

### Required repair

Provider failure must not become internal success.

Use explicit result states such as:
- SENT;
- FAILED;
- UNKNOWN;
- RETRYABLE.

Only publish `message_sent` after provider-confirmed success.

### Acceptance

Provider failure:
- no false SENT;
- no false success event;
- retry behavior bounded;
- audit captures failure.

---

## R3-002 — Message idempotency

**Priority:** P1

Add robust uniqueness for tenant + external provider message identity where applicable.

Handle:
- duplicate webhook;
- retry;
- race;
- concurrent workers.

### Acceptance

Same provider message cannot create duplicate logical messages.

---

## R3-003 — Webhook parser correctness

**Priority:** P1

Ensure each incoming webhook entry/change is parsed according to its unit of work.

Do not pass an entire batch to a parser designed for one message.

Acceptance:
- multi-entry payload;
- multiple messages;
- duplicate delivery;
- malformed entry;
- partial processing.

---

## R3-004 — Customer response ownership

**Priority:** P1

Strengthen conversation/handoff state so AI and human cannot race to respond.

Required concept:
- AI-owned;
- human-owned;
- handoff pending;
- human handling;
- resolved/closed where applicable.

Automation/follow-up must respect human ownership.

---

## R3-005 — Customer identity normalization

**Priority:** P1

Use deterministic normalized phone identity appropriate to the WhatsApp provider.

Avoid exact-string-only identity matching.

Acceptance:
- equivalent phone formats map consistently;
- different tenants remain isolated;
- duplicate customer creation is prevented.

---

# 9. R4 — AI GATEWAY / AI RUNTIME SAFETY

## R4-001 — Distributed rate limiting

**Priority:** P1

### Finding

In-memory rate limiter instantiated per gateway instance does not provide shared enforcement across workers.

### Required repair

Use shared/distributed enforcement for production where multiple workers/instances exist.

Do not weaken rate limiting merely for test convenience.

Acceptance:
- multiple worker/process scenario;
- quota/rate limit is consistent;
- fail behavior is defined.

---

## R4-002 — Atomic AI usage enforcement

**Priority:** P1

### Finding

Usage check/read and usage insert are not sufficiently atomic; exceptions may be swallowed.

### Required repair

Create a deterministic usage reservation/consumption mechanism.

It must distinguish:
- usage accounting;
- entitlement;
- quota;
- budget;
- billing.

Usage enforcement must fail safely.

Acceptance:
- concurrent requests cannot oversubscribe uncontrollably;
- DB failure does not silently grant unlimited AI;
- retries do not double-charge usage incorrectly;
- tenant attribution is correct.

---

## R4-003 — Provider failure/fallback behavior

**Priority:** P1

### Finding

Primary provider failure path does not provide a robust production strategy.

### Required repair

Implement only the provider fallback behavior actually supported by architecture/configuration.

At minimum define:
- timeout;
- retry;
- retry budget;
- UNKNOWN;
- degraded mode;
- user-facing safe fallback;
- audit.

Do not invent an unapproved provider.

---

## R4-004 — Runtime guardrail enforcement

**Priority:** P1

### Finding

Guardrails exist as stored/readiness data, but a complete runtime enforcement layer was not found.

### Required repair

Ensure high-risk AI outputs/actions pass runtime policy/guardrail evaluation before execution.

Guardrails must be enforceable, not documentation-only.

Acceptance:
- prohibited action blocked;
- missing guardrail configuration fails safe where required;
- AI output cannot become authority by itself.

---

## R4-005 — Deterministic-first transactional truth

**Priority:** P1

For price, stock, payment, order state and permissions:
- deterministic authoritative data first;
- AI reasoning cannot override source of truth;
- volatile values revalidated at transaction boundary.

---

# 10. R5 — WORKFLOW / EVENT / ACTION INTEGRITY

## R5-001 — False-success workflow handlers

**Priority:** P1

### Affected examples

- `update_customer`
- `update_order`
- `change_product_price`
- `issue_refund`

### Required repair

Every action must return success only after the actual state-changing operation succeeds.

If action requires approval:
- return `REQUIRES_APPROVAL` / WAITING state;
- never SUCCESS.

If provider result is unknown:
- UNKNOWN;
- reconciliation path.

Acceptance tests must inspect actual DB/provider state, not merely returned status.

---

## R5-002 — Event failure / dead-letter handling

**Priority:** P1

### Finding

Some event handlers may be ACKed after failure.

### Required repair

Define:
- retryable failure;
- permanent failure;
- dead-letter;
- reclaim;
- visibility timeout;
- audit.

Do not ACK failed work as successful.

---

## R5-003 — Cross-event workflow loops

**Priority:** P1

Per-execution step limits are insufficient if each event creates a new execution.

### Required repair

Add bounded causality controls:
- correlation ID;
- parent execution;
- loop detection;
- trigger depth;
- time budget;
- execution budget;
- repeated-event suppression.

Acceptance:
- A→B→A event cycle terminates safely.

---

## R5-004 — Integration action authorization

**Priority:** P1

`allow_internal=True` cannot become an authorization bypass.

Every integration action must still evaluate:
- tenant;
- actor;
- permission;
- entitlement;
- policy;
- risk;
- approval where required.

---

# 11. R6 — DATA INTEGRITY / IDENTITY / MEMORY / TENANT FK

## R6-001 — Cross-tenant FK integrity

**Priority:** P1

Review parent-child relations where tenant ownership is currently enforced mainly by application code.

Where required by the domain, enforce tenant consistency at the database/application boundary.

Do not add redundant constraints merely because IDs are globally unique.

Acceptance:
- child cannot reference another tenant's parent;
- application and DB protections agree;
- historical records remain valid.

---

## R6-002 — Client memory ownership

**Priority:** P1

### Finding

`ClientMemory` uniqueness is tenant + key, while customer identity is stored indirectly.

### Required repair

Memory records must have explicit customer/subject scope where memory is customer-specific.

Memory must not:
- override authoritative business data;
- cross customers;
- cross tenants;
- become global learning automatically.

---

## R6-003 — Data / knowledge / memory boundary

**Priority:** P1

Preserve separation:

`Authoritative DB ≠ Knowledge ≠ Conversation ≠ Memory ≠ AI reasoning`

Retrieval must enforce authorization and tenant scope.

---

# 12. R7 — ENTITLEMENT / PLAN / PRODUCT ALIGNMENT

## R7-001 — Business plan conflict

**Priority:** P1

### Finding

Repository currently exposes Business features such as Owner AI/internal-style capabilities, advanced BI and multi-channel capabilities that conflict with the current product direction where Business is future.

### Required repair

Reconcile repository plan definitions with the canonical product scope.

Do not invent Business scope.

At minimum:
- Starter remains baseline;
- Pro is current serious target;
- Business remains future unless explicitly promoted by the Owner;
- internal AI BOS roles are not tenant plan features.

### Acceptance

Plan feature matrix matches the canonical blueprint and Q1–Q51.

---

## R7-002 — Service onboarding stock conflict

**Priority:** P1

### Finding

Onboarding validation appears to require stock for active products/services despite Product and Service being distinct.

### Required repair

Product stock requirements and Service fields must be evaluated separately.

A service must not be forced into product-stock semantics.

---

## R7-003 — Entitlement enforcement consistency

**Priority:** P1

Audit every feature entry point:
- API;
- workflow;
- integration;
- AI;
- outbound message;
- automation.

No alternate internal path may silently bypass entitlement.

---

# 13. R8 — CI/CD / DEPENDENCY REPRODUCIBILITY

## R8-001 — Runtime dependencies not fully declared

**Priority:** P1

### Finding

CI installs dependencies not fully reflected in `pyproject.toml`.

### Required repair

Make project dependency declaration authoritative and reproducible.

Acceptance:
- clean environment installation;
- tests run without undocumented manual package installation;
- lock/version policy is coherent.

---

## R8-002 — CI workflow correctness

**Priority:** P1

### Finding

Workflow is manually dispatched and references a historical PR rather than behaving as normal push/PR CI.

### Required repair

Align CI triggers with repository development policy.

Required:
- pull request validation;
- push validation where appropriate;
- migration tests;
- security/tenant tests;
- full regression;
- no hardcoded historical PR dependency.

---

# 14. R9 — P2 PRODUCTION HARDENING

## R9-001 — Backup/restore/DR evidence

**Priority:** P2 now; production gate later

Define and test:
- backup;
- restore;
- tenant isolation after restore;
- audit/history preservation;
- external side-effect reconciliation;
- RPO/RTO values when Owner decides them.

---

## R9-002 — Retention/deletion/export

**Priority:** P2

Implement explicit lifecycle for:
- tenant data;
- customer data;
- conversations;
- knowledge;
- memory;
- audit;
- exports;
- backups.

No silent deletion policy invention.

---

## R9-003 — Authentication hardening

**Priority:** P2

Review:
- login brute-force;
- MFA readiness;
- password reset;
- session invalidation;
- credential abuse protection.

---

## R9-004 — Frontend token storage

**Priority:** P2

Review localStorage JWT exposure and adopt a safer session/token model compatible with the existing architecture.

Do not introduce a breaking auth redesign without explicit approval.

---

## R9-005 — Observability

**Priority:** P2

Improve production observability for:
- metrics;
- logs;
- traces;
- audit;
- correlation;
- workflow execution;
- AI latency;
- AI cost/usage;
- incidents;
- webhook delivery;
- queue health.

Never log secrets or sensitive AI context.

---

## R9-006 — Internal AI implementation alignment

**Priority:** P2/P1 depending on Pro acceptance scope

Verify implementation against the internal AI architecture:
- Owner AI;
- Reception AI;
- Sales AI;
- Client Manager AI;
- Support/Client Support/Admin AI;
- Data/Knowledge AI;
- Analyst AI;
- AI Technician.

Do not expose these as tenant-plan capabilities merely because internal implementations exist.

---

# 15. REPAIR EXECUTION RULES

For every repair:

1. Inspect current code.
2. Identify root cause.
3. Map to finding ID.
4. Make minimum safe change.
5. Reuse existing subsystem.
6. Add or update tests.
7. Run targeted tests.
8. Run relevant phase tests.
9. Run regression.
10. Review security.
11. Review tenant isolation.
12. Review idempotency.
13. Review migration.
14. Review OpenAPI where API changed.
15. Record evidence.
16. Mark finding:
   - RESOLVED
   - PARTIALLY RESOLVED
   - BLOCKED
   - NOT REPRODUCED
17. Do not mark PASS without evidence.

---

# 16. REQUIRED REPAIR EVIDENCE

Each repair batch must produce:

```text
REPAIR BATCH REPORT

Batch:
Status:

Findings addressed:
-

Root causes:
-

Files changed:
-

Models:
-

Services:
-

APIs:
-

Events:
-

Workflows:
-

Permissions:
-

Tenant isolation:
-

Security:
-

Idempotency:
-

Migration:
-

Tests added:
-

Targeted tests:
-

Regression:
-

OpenAPI:
-

Configuration:
-

Known limitations:
-

Out of scope:
-

Architecture changes:
-

Evidence:
-

Remaining P0:
-

Remaining P1:
-

Remaining P2:
-

Final recommendation:
PASS / FAIL / BLOCKED
```

---

# 17. REQUIRED SECURITY TEST MATRIX

At minimum test:

| Scenario | Expected |
|---|---|
| No JWT + tenant ID | DENY |
| Invalid JWT | DENY |
| Tenant A actor → Tenant B | DENY |
| Valid actor, insufficient permission | DENY |
| Suspended tenant | DENY where applicable |
| Workflow internal flag bypass | DENY if unauthorized |
| External event → privileged action | DENY without authority |
| Invalid webhook signature | DENY |
| Replay webhook | Idempotent/no duplicate effect |
| Wrong payment amount | DENY / reconciliation |
| AI tries to override stock | DENY |
| AI tries to bypass policy | DENY |
| Missing guardrail | FAIL SAFE |
| Provider timeout | UNKNOWN/recovery |
| Duplicate message | No duplicate logical record |
| Event handler failure | Retry/DLQ, not false ACK |
| Workflow loop | Bounded/terminated |
| Cross-tenant memory retrieval | DENY |
| Cross-tenant FK reference | DENY |
| Quota exhaustion | DENY/controlled degradation |
| Expired subscription | Entitlement denied |

---

# 18. REQUIRED GOLDEN PATH REGRESSION

## Path A — Tenant access

`Login → authenticated actor → tenant selection → authorized dashboard`

## Path B — WhatsApp customer

`Webhook → identify tenant → identify customer → conversation → AI → grounded response`

## Path C — Product discovery

`Customer → product query → authoritative product data → recommendation → no hallucinated price/stock`

## Path D — Commerce

`Product → variant → cart → checkout → validation → order → payment → verification → PAID`

## Path E — Human handoff

`AI → trigger → handoff package → human owns response → automation suppression`

## Path F — Workflow

`Event → trigger → condition → action → verification → result → audit`

## Path G — Billing

`Subscription → payment → webhook → verification → entitlement → expiry`

## Path H — AI usage

`Request → entitlement/quota/budget → AIGateway → usage accounting → response`

---

# 19. STOP CONDITIONS

The executor MUST STOP and report instead of guessing if:

- a repair requires changing Q1–Q51;
- two canonical sources conflict;
- product scope is ambiguous;
- authority cannot be determined;
- tenant ownership cannot be determined;
- payment truth cannot be reconciled;
- a migration would destroy existing data;
- a security boundary cannot be safely repaired;
- required external credentials/provider behavior is unavailable;
- a repair creates a new architecture rather than fixing an implementation defect;
- a P0/P1 remains after the attempted repair;
- tests pass only because a safety control was weakened;
- an implementation requires undocumented assumptions.

---

# 20. BRANCH & GITHUB SAFETY

All repairs must be performed on a dedicated non-main branch.

Recommended:

`feature/ai-bos-repair-hardening`

Flow:

```text
main
  ↓
repair branch
  ↓
R0
  ↓
R1
  ↓
R2
  ↓
...
  ↓
targeted tests
  ↓
regression
  ↓
independent audit
  ↓
PR
  ↓
STOP
```

Never:
- force-push main;
- merge main autonomously;
- delete stable history;
- rewrite production history without authorization.

---

# 21. REPAIR DEFINITION OF DONE

A repair is DONE only when:

- root cause is addressed;
- original behavior remains within architecture;
- relevant requirement is preserved;
- tenant isolation is verified;
- permissions are verified;
- security is verified;
- state transitions are verified;
- idempotency is verified where applicable;
- migrations are verified;
- tests exist;
- targeted tests pass;
- regression passes;
- OpenAPI is updated where applicable;
- no hardcoded production secrets;
- no unsafe shell/arbitrary SQL introduced;
- no unrelated scope added;
- evidence is recorded;
- independent review does not identify a remaining critical issue.

---

# 22. FINAL REPAIR EXIT GATE

The repair stage may exit only when:

```text
P0 findings
    = 0 unresolved
        AND
P1 findings
    = 0 unresolved
        AND
Targeted security tests
    = PASS
        AND
Tenant isolation tests
    = PASS
        AND
Payment integrity tests
    = PASS
        AND
WhatsApp E2E tests
    = PASS
        AND
Workflow/Event integrity tests
    = PASS
        AND
AI runtime safety tests
    = PASS
        AND
Migration tests
    = PASS
        AND
Full regression
    = PASS
        AND
Independent audit
    = PASS
```

P2 items may remain only if explicitly documented, accepted by the Owner, and proven not to block the intended build stage.

---

# 23. POST-REPAIR AUDIT

After implementation:

1. Re-run the original audit against the current repository.
2. Re-check every original finding.
3. Search for regressions introduced by repairs.
4. Search for duplicate systems created during repair.
5. Re-check Q1–Q51 alignment.
6. Re-check Pro scope.
7. Re-check tenant isolation.
8. Re-check deterministic-first transaction truth.
9. Re-check AI authority boundaries.
10. Re-check billing authority.
11. Re-check workflow/event causality.
12. Re-check observability.
13. Re-check production configuration.
14. Produce a new PASS/FAIL/NO-GO report.

A repaired repository does not automatically become PASS.

---

# 24. IMPORTANT PRODUCT BOUNDARY

This repair plan does NOT authorize:

- adding all future Business features;
- turning internal AI into tenant features;
- adding unrestricted autonomy;
- building advanced ERP/POS;
- advanced warehouse/accounting;
- automatic fulfillment/waybill;
- global tenant learning;
- unrestricted cross-tenant access;
- arbitrary custom agent capabilities;
- production deployment;
- merge to main.

The target remains the agreed AI BOS direction with **Pro as the current serious product target**, while Starter remains the baseline and Business/future capabilities remain controlled.

---

# 25. MASTER REPAIR COMMAND FOR JULES / COPILOT

Use this as the implementation instruction:

> REPAIR AND HARDEN THE EXISTING AI BOS REPOSITORY.
>
> Do NOT rebuild AI BOS.
>
> Treat the existing repository as the implementation subject and this Repair Plan as the repair specification.
>
> Read:
>
> - the canonical Master Blueprint;
> - locked decisions Q1–Q51;
> - the Master Execution Plan;
> - this Master Repair Plan;
> - the current repository.
>
> Before changing code, revalidate each listed finding against the current repository. A historical finding is not automatically current truth.
>
> Work only on a dedicated non-main branch.
>
> Repair findings in dependency order, starting with P0.
>
> Preserve the existing Universal Core and module boundaries. Reuse existing services, repositories, adapters, AIGateway, workflow/event systems, billing systems, approval systems and tenant controls where appropriate.
>
> Do not create duplicate architecture.
>
> Do not silently change Q1–Q51.
>
> Do not invent missing product decisions.
>
> Do not convert future Business/internal-AI capabilities into current tenant features unless explicitly authorized.
>
> For every repair:
>
> 1. inspect;
> 2. identify root cause;
> 3. map to finding ID;
> 4. implement the minimum safe repair;
> 5. add/update tests;
> 6. run targeted tests;
> 7. run relevant regression;
> 8. review security;
> 9. review tenant isolation;
> 10. review permissions;
> 11. review idempotency;
> 12. review migrations;
> 13. update API/OpenAPI where required;
> 14. record evidence.
>
> NEVER make tests pass by weakening security or business controls.
>
> NEVER use AI output as authorization.
>
> NEVER let tenant ID replace authentication.
>
> NEVER let workflow internal flags bypass permission, entitlement, policy, risk or approval.
>
> NEVER allow fake payment infrastructure to silently operate as production payment authority.
>
> NEVER report provider failure as success.
>
> NEVER acknowledge failed event handling as successful.
>
> NEVER allow duplicate webhook/message delivery to create duplicate logical effects.
>
> NEVER allow cross-tenant data, memory, events, workflow execution or integration access.
>
> If a P0/P1 blocker, architecture conflict, missing decision, unsafe ambiguity, destructive migration risk, or required external dependency prevents safe repair, STOP and report it.
>
> After repairs, run targeted security, tenant isolation, payment, WhatsApp, AI runtime, workflow/event, migration and full regression tests.
>
> Produce a complete repair batch report and final repair report.
>
> Do not merge to main.
>
> Do not declare FINAL PASS yourself merely because tests pass.
>
> The final PR must remain unmerged for independent audit and Project Owner approval.

---

# 26. FINAL STATUS TEMPLATE

```text
AI BOS REPAIR & HARDENING FINAL REPORT

Repository:
Branch:
Commit:

Original audit status:
NO-GO

P0 original:
Total:
Resolved:
Remaining:

P1 original:
Total:
Resolved:
Remaining:

P2 original:
Total:
Resolved:
Remaining:

Migration:
PASS / FAIL

Security:
PASS / FAIL

Tenant isolation:
PASS / FAIL

Billing:
PASS / FAIL

WhatsApp:
PASS / FAIL

AI runtime:
PASS / FAIL

Workflow/Event:
PASS / FAIL

Data integrity:
PASS / FAIL

Entitlement/Product alignment:
PASS / FAIL

CI/CD:
PASS / FAIL

Targeted tests:
PASS / FAIL

Full regression:
PASS / FAIL

OpenAPI:
PASS / FAIL / N/A

Independent audit:
PASS / FAIL / BLOCKED

Final recommendation:
GO / NO-GO

Known limitations:
-

Deferred items:
-

Architecture changes:
-

Evidence:
-
```

---

# 27. MASTER PRINCIPLE

> The objective of this stage is not to write more code.
>
> The objective is to make the existing AI BOS implementation conform to its already-approved architecture and safety contract.

```text
AUDIT
  ↓
REPAIR SPECIFICATION
  ↓
REVALIDATE FINDING
  ↓
MINIMUM SAFE REPAIR
  ↓
TARGETED TEST
  ↓
SECURITY + TENANT REVIEW
  ↓
REGRESSION
  ↓
RE-AUDIT
  ↓
FINAL PASS
  ↓
PR
  ↓
OWNER APPROVAL
  ↓
MERGE
```

**No critical shortcut.**
**No silent architecture change.**
**No autonomous merge.**
**No PASS without evidence.**
