# AI BUSINESS OPERATING SYSTEM
# LOCKED ARCHITECTURE & BEHAVIOR DECISIONS
## ACT-001 → ACT-090

> Status: LOCKED
> 
> This document records decisions agreed during the AI BOS architecture discussion.
> These decisions are the working source for future design discussions until explicitly changed.

---

## STAGE 1–3 — SYSTEM, ACTORS, SALES & ONBOARDING

### ACT-001 — Human Owner Authority
**Status: ACTIVE**
Human Owner is the highest human authority and final decision maker.

### ACT-002 — Human Admin Authority
**Status: ACTIVE**
Human Admin may perform low-risk actions. Medium-risk actions require explicit Human Owner permission. No high-risk/critical authority.

### ACT-003 — Client Identity & Lifecycle
**Status: ACTIVE**
Client identity/lifecycle is separate from sales. A new contact is not automatically a Client/Tenant.
Lifecycle:
PROSPECT → LEAD → QUALIFIED → PROPOSAL → WAITING_PAYMENT → PAID → CLIENT/TENANT → ONBOARDING → CONFIGURING → TESTING → READY → ACTIVE.
Special states may include BLOCKED, WAITING_OWNER, WAITING_CLIENT, ERROR.

### ACT-004 — First Contact
**Status: ACTIVE**
Default: short AI BOS explanation + value proposition + ask the prospect's need. Adaptive behavior is allowed. Do not immediately force tenant creation, forms, or payment.

### ACT-005 — Non-Pressuring Sales
**Status: ACTIVE**
AI Sales serves browsers politely and acts as a consultant, not a pushy salesperson.

### ACT-006 — Owner AI Role
**Status: ACTIVE**
Owner AI is the business brain, BI layer and orchestrator:
DATA → ANALYSIS → INSIGHT → RECOMMENDATION → TASK/ACTION → RESULT → EVALUATION.
It can use relevant data, recommend, delegate, monitor and report. It handles natural commands, clarifies ambiguity, and requires approval for high-risk actions.

### ACT-007 — Owner AI Data Access
**Status: ACTIVE**
Human Owner has broad authority. Owner AI may access business/platform/customer/usage/billing/error/audit/operations data required for its role. Tenant AI is restricted to its own tenant. Cross-tenant analytics is allowed for Owner AI when requested, but not unrestricted database dumping.

### ACT-008 — Owner AI Secrets
**Status: ACTIVE**
Owner AI does not receive unrestricted access to secrets/credentials.

### ACT-009 — Proactive Owner AI
**Status: ACTIVE**
Owner AI may proactively surface significant alerts, monitor delegated tasks, verify/evaluate outcomes and report them, with appropriate filtering.

### ACT-010 — Future AI Thinking Partner
**Status: FUTURE**
A future Thinking Partner may use external research and explicitly provided business documents. It does not directly access BOS DB, production, credentials or operations by default.

### ACT-011 — Conversation Continuity
**Status: ACTIVE**
Dedicated continuity exists for Owner ↔ Owner AI and Prospect ↔ Sales. Memory scopes include Owner, Prospect, Tenant, Customer and System. DB remains the factual source. Do not stuff entire history into the model.

### ACT-012 — Deferred Owner Instruction
**Status: ACTIVE**
Target-specific instructions may be stored even if the target does not yet exist:
WAITING_FOR_TARGET → later match → validate → execute → verify → report.
Ambiguous instructions require clarification.

### ACT-013 — Owner AI End-to-End Execution
**Status: ACTIVE**
Human Owner → Owner AI → analysis → planning → delegation → monitoring → verification → evaluation → audit/memory → report.
High-risk actions wait for approval.

### ACT-014 — First Contact Default
**Status: ACTIVE**
First-contact behavior remains C default + D adaptive.

### ACT-015 — Prospect Qualification
**Status: ACTIVE**
Use adaptive exploration of needs + solution explanation + offer.

### ACT-016 — Package Recommendation
**Status: ACTIVE**
Recommend the best fit, relevant features and lower/higher alternatives. No pressure. Pricing/features/promos/entitlements come from system data.

### ACT-017 — Purchase Flow
**Status: ACTIVE**
Confirm package/price/period → order/payment request → payment link/invoice → verified gateway/webhook → subscription active → Client Manager onboarding.
Payment system is the source of truth.

### ACT-018 — Post-Payment Handoff
**Status: ACTIVE**
Sales finishes after purchase. Client Manager owns onboarding/lifecycle. Owner AI monitors. Support/Data Manager assist where needed.

### ACT-019 — Progressive Onboarding
**Status: ACTIVE**
Onboarding is flexible across chat, dashboard, form, Excel/CSV/spreadsheet and API.

### ACT-020 — Adaptive Data Collection
**Status: ACTIVE**
Collection adapts to business type, needs, plan/features, existing/missing data, integrations and progress, while mandatory requirements remain fixed.

### ACT-021 — Requirement Determination
**Status: ACTIVE**
Requirement Engine determines onboarding requirements from plan + business type + enabled features + Universal Core minimum, using known client/business/features/existing data.

### ACT-022 — Business Type Change
**Status: ACTIVE**
Detect → assess → explain → confirm when important → Change Request → recalculate → update onboarding plan → revalidate affected capabilities.
No silent changes and no unnecessary restart.

### ACT-023 — AI-Assisted Product Import
**Status: ACTIVE**
Photo → extraction → draft → client review → official data.
AI must not guess active facts.

### ACT-024 — Smart Import Validation
**Status: ACTIVE**
Import statuses: VALID / NEEDS_REVIEW / CONFLICT / ERROR.
Safe formatting may be auto-fixed. Sensitive fields (price, stock, variants, sizes, SKU, discounts, promos, payment/return/refund policy) require client validation. AI does not choose unresolved conflicts.

### ACT-025 — Natural Language to Policy/Workflow
**Status: ACTIVE**
AI interprets and structures natural language. System stores, validates, executes and audits. Critical rules are not executed solely by AI interpretation.

### ACT-026 — AI Permission Configuration
**Status: ACTIVE**
Natural language → draft → entitlement/security validation → client review → confirmation → active.
AI cannot exceed entitlement.

### ACT-027 — Pre-Activation Gate
**Status: ACTIVE**
Automated test → analysis → safe fix/delegate → retest → client test → evaluate → READY → ACTIVE.
Evidence gate required.

### ACT-028 — Inactive Follow-Up
**Status: ACTIVE**
Use bounded scheduled follow-ups/reminders, then WAITING_CLIENT. Do not incorrectly mark as failed/completed. Owner AI is informed when significant.

### ACT-029 — Package Upgrade
**Status: ACTIVE**
Explain Starter/Pro → confirm need → upgrade transaction → verified payment → entitlement update → recalculate onboarding.
AI does not directly alter billing.

### ACT-030 — Human Assistance
**Status: ACTIVE**
Handoff to the appropriate human/support role with full onboarding context. Client Manager monitors. After resolution: verify → resume.

### ACT-031 — Technical Issue
**Status: ACTIVE**
Client Manager detects → AI Support diagnoses/troubleshoots safely → retest.
If unresolved/high-risk → incident/task → human escalation. Owner AI monitors significant incidents.

### ACT-032 — Unresolved Data Conflict
**Status: ACTIVE**
Set CONFLICT/WAITING_CLIENT. Do not use uncertain sensitive values. Continue unaffected onboarding, create follow-up, resume after confirmation.

### ACT-033 — Pause/Resume
**Status: ACTIVE**
Onboarding becomes PAUSED while preserving validated progress and stopping reminders. Subscription state is checked separately. Resume from the preserved point. Onboarding state != subscription state.

### ACT-034 — Cancellation
**Status: ACTIVE**
Explain/confirm → billing-system cancellation → optional pause/downgrade alternatives → refund/compensation requires appropriate approval → monitor final status/report.
Cancellation does not automatically mean immediate tenant/data deletion.

### ACT-035 — WhatsApp Connection Issue
**Status: ACTIVE**
Troubleshoot → AI Support → incident/task if unresolved → WAITING_TECHNICAL_ISSUE → human escalation → Owner AI monitors significant issue → verify/resume.

### ACT-036 — Partial Activation
**Status: ACTIVE**
Check capability dependencies. Ready capabilities may activate while unready capabilities are disabled/pending. Critical dependencies still block activation.

### ACT-037 — Subscription Issue
**Status: ACTIVE**
Billing system is source of truth. Client Manager adjusts capability visibility, informs client, preserves onboarding and creates tasks/follow-up. Owner AI monitors significant issues. When active, recalculate entitlement and resume.

### ACT-038 — Trial Expiry
**Status: ACTIVE**
Follow billing/entitlement state. Preserve onboarding, inform client and provide options. Owner AI monitors significant impact. AI cannot self-extend/reactivate/compensate.

### ACT-039 — Stale Onboarding
**Status: ACTIVE**
After bounded follow-up and prolonged inactivity:
ONBOARDING → STALE.
Stop active reminders, preserve progress, Owner AI evaluates significance, subscription continues according to billing, and onboarding can resume when service permits.
STALE != CANCELLED != CHURNED.

### ACT-040 — Missing Business Policy
**Status: ACTIVE**
Explain the need → AI may help draft from client-provided information → DRAFT → client review/confirmation → official policy.
High-risk/legal/financial policy requires special confirmation.

### ACT-041 — AI-Assisted Business Decision
**Status: ACTIVE**
AI analyzes, presents options/recommendation and creates drafts. Client chooses/edits. High-risk decisions go through appropriate approval. AI does not silently decide.

### ACT-042 — Early Activation
**Status: FUTURE**
Client may request early activation. Check capability dependencies/security/readiness. Ready capabilities can activate; unready ones remain disabled/pending. No bypass of critical safety/security.

### ACT-043 — Conflicting Business Data
**Status: ACTIVE**
Detect conflict → show provenance/history → client selects final value → official update → version/audit → retest affected capability. Historical truth remains retained.

### ACT-044 — Multiple Businesses per Owner
**Status: ACTIVE**
One Human Owner may own multiple isolated business/tenant scopes. Business/customer/product/knowledge/workflow/analytics/memory/integration/config data remains isolated per scope. Owner may manage across scopes.

### ACT-045 — Multiple WhatsApp Numbers per Tenant
**Status: ACTIVE**
A tenant may have multiple WhatsApp numbers. Each channel has identity, role, permissions, routing, workflow, conversation context and escalation. System always knows the source channel. Owner channel is handled according to its role.

### ACT-046 — READY → ACTIVE
**Status: ACTIVE**
If activation was already approved and all gates pass, system may auto-activate. Otherwise request confirmation. Post-activation verification and onboarding report are required.

---

## STAGE 4 — BUSINESS DATA & KNOWLEDGE GOVERNANCE

### ACT-047 — Business Data Source of Truth & Conflict Gate
**Status: ACTIVE**
Hierarchy:
1. DB/System
2. Business Configuration
3. Approved Knowledge
4. Conversation Context
5. AI Reasoning

If a relevant unresolved conflict exists, do not use uncertain data for sensitive transactions. Identify provenance, ask authorized clarification, update official data, version/audit, validate, then use.

### ACT-048 — Business Data Change Authorization
**Status: ACTIVE**
AI may interpret a natural-language change and create a Change Request, explain impact, validate, request confirmation/approval and execute only when the actor has permission. Verify, version and audit the result.
Customer cannot change business data. AI cannot silently change official data.

### ACT-049 — Post-Activation Business Data Change
**Status: ACTIVE**
Change Request → Authorization → Update Official Data → Versioning/Audit → identify dependencies → refresh/invalidate relevant cache/context → test affected workflows → verify → emit `business_data.updated` → agents use the new value.
Historical conversations retain prior truth; new conversations use current official data.

### ACT-050 — Missing Data
**Status: ACTIVE**
Do not invent. Tell the user the information is unavailable, provide a valid fallback/handoff where appropriate, and log a missing-data signal.

### ACT-051 — Expired Knowledge
**Status: ACTIVE**
OUTDATED → review/update → use again only when valid/active.

### ACT-052 — Expiry by Data Type
**Status: ACTIVE**
Freshness/expiry policy is defined per data type, with controlled Owner override.

### ACT-053 — Price Change with Open Order
**Status: ACTIVE**
Order stores a snapshot such as `unit_price_at_order`. Catalog changes apply to new transactions unless there is an explicit official adjustment.

### ACT-054 — Volatile Stock
**Status: ACTIVE**
Use current system data plus a final deterministic availability check at transaction commit.

### ACT-055 — Customer-Provided Promo Claim
**Status: ACTIVE**
Treat unverified promo claims as unverified. Verify against official data/authorized confirmation before treating them as active facts.

### ACT-056 — Customer Claims Business Address Changed
**Status: ACTIVE**
Treat the claim as unverified. Verify and require authorized business-data change, with versioning and audit.

### ACT-057 — Knowledge vs Pricing/Promotion Engine Conflict
**Status: ACTIVE**
Transaction/business engine is authoritative. Conflicting knowledge cannot drive a transaction until verified.

### ACT-058 — Deleting Business Data
**Status: ACTIVE**
Default to archive/deactivate plus dependency checks. Hard delete only where policy permits and safety/dependency checks pass.

### ACT-059 — Discontinued Product
**Status: ACTIVE**
Deactivate/archive for new sales while retaining historical references.

### ACT-060 — Source Transparency
**Status: ACTIVE**
Customers receive natural, relevant transparency. Human Owner/Admin receive detailed provenance/audit according to permission.

### ACT-061 — Data Read Access
**Status: ACTIVE**
Access follows role + tenant scope + permission + purpose. Use RBAC, tenant isolation and least privilege. Secrets remain protected.

### ACT-062 — Minimum Necessary Context
**Status: ACTIVE**
AI receives only the minimum data necessary for the current task/agent/permission. Context requests are policy-controlled and auditable.

### ACT-063 — Search Finds No Data
**Status: ACTIVE**
Verify search → do not invent → explain missing information → offer valid alternatives or handoff → optionally log a knowledge/data gap.

### ACT-064 — Semantic Candidate Match
**Status: ACTIVE**
Semantic search may find candidate matches, but candidate similarity does not become factual equivalence. Ask/confirm when needed.

### ACT-065 — Configuration vs Knowledge
**Status: ACTIVE**
Structured operational Business Configuration has authority over conflicting operational knowledge. Conflicts in knowledge go to review.

### ACT-066 — Concurrent Business Data Change
**Status: ACTIVE**
Use version-aware context and current-source verification. Transactions/actions require current official data at their consistency boundary.

### ACT-067 — Large Bulk Update
**Status: ACTIVE**
Upload → Validate → Preview → Diff → Classify → review sensitive/conflicting fields → Approve → controlled batch apply → Verify → Audit.

### ACT-068 — Partial Bulk Update Failure
**Status: ACTIVE**
Support controlled partial success with per-record status. Valid records may proceed according to policy; conflicts/errors remain for review/retry. Report all results.

### ACT-069 — Duplicate Product
**Status: ACTIVE**
Detect possible duplicates. Offer merge/keep separate/archive/review. Ambiguous duplicates require confirmation; no unsafe automatic merge.

### ACT-070 — Dependency-Aware Business Data Change
**Status: ACTIVE**
For changes affecting multiple workflows:
Change Request → impact analysis → dependency detection → authorization → update → refresh affected workflows/config → tests → verification → event → audit.

---

## STAGE 5 — KNOWLEDGE BASE & AI RETRIEVAL

### ACT-071 — Knowledge Types
**Status: ACTIVE**
Knowledge is typed, e.g. FAQ, SOP, Policy, Product Information, Promotion, Business Information, Customer-facing Information, Internal Information, Legal/Compliance, Operational Instructions.
Metadata includes type, scope, audience, status, version, source and relevant lifecycle metadata.

### ACT-072 — Internal vs Customer-Facing Knowledge
**Status: ACTIVE**
Knowledge has audience/visibility/allowed-agent/role/tenant scope. Internal information must not leak to customers.

### ACT-073 — Knowledge Versioning
**Status: ACTIVE**
Use the valid ACTIVE version. Historical versions remain stored for audit/history.

### ACT-074 — Unapproved Knowledge
**Status: ACTIVE**
DRAFT/VALIDATING knowledge is not treated as official customer-facing fact. It may be used in explicitly permitted internal preview/review contexts.

### ACT-075 — Conflicting ACTIVE Knowledge
**Status: ACTIVE**
Do not let the LLM choose arbitrarily. Detect conflict → inspect source/provenance/priority → if unresolved, mark conflict/escalate and do not use it for sensitive decisions.

### ACT-076 — Missing Knowledge
**Status: ACTIVE**
No hallucinated SOP/policy. Provide graceful fallback/handoff and log a `knowledge_gap_detected` signal where useful.

### ACT-077 — Relevant Semantic Knowledge
**Status: ACTIVE**
Semantic retrieval may identify relevant knowledge. Generation must remain grounded in the official content and may not add unsupported rules.

### ACT-078 — Relevant Context Only
**Status: ACTIVE**
Do not send the entire knowledge base to the model. Retrieve relevant context subject to relevance threshold, token/context budget, source priority, freshness, tenant isolation and permissions.

### ACT-079 — Source Transparency
**Status: ACTIVE**
Customer-facing source information is natural and relevant, not raw internal metadata. Authorized Owner/Admin views expose detailed provenance.

### ACT-080 — Expired Knowledge
**Status: ACTIVE**
Expired knowledge becomes OUTDATED and is excluded from active factual retrieval unless an explicitly authorized historical context requires it. Current active knowledge is preferred.

---

## STAGE 5 — AI CONVERSATION & CONTEXT MANAGEMENT

### ACT-081 — Customer Returns After Several Days
**Status: ACTIVE**
Use conversation history/summary, relevant customer memory, current business data and current task context. Do not resend the entire raw history to the model.

### ACT-082 — Long Conversation
**Status: ACTIVE**
Use hierarchical context:
Recent Messages + Conversation Summary + Relevant Customer Memory + Current Task + Relevant Business Data + Relevant Knowledge.
Keep complete history in storage.

### ACT-083 — Multiple Customer Conversations
**Status: ACTIVE**
Sales, Support, Order, Complaint, etc. remain logically distinct conversations while being linked to the same Customer identity. Agents receive only relevant conversation context.

### ACT-084 — Dynamic Agent Routing
**Status: ACTIVE**
When customer intent changes (e.g. Sales → Support), dynamically route to the appropriate agent/task and carry relevant context.

### ACT-085 — Structured Agent Handoff
**Status: ACTIVE**
Agent handoff transfers relevant structured context: customer, product/order, status, related conversation, previous actions and relevant knowledge. Do not transfer unrestricted internal chain-of-thought.

### ACT-086 — Selective Memory
**Status: ACTIVE**
Not every conversation statement becomes permanent memory. Candidate memory is extracted selectively, validated by policy and stored in structured memory.

### ACT-087 — Memory Correction
**Status: ACTIVE**
When a customer changes a remembered preference, detect conflict, update the current validated memory and retain historical information where appropriate.

### ACT-088 — Current Explicit Information Wins
**Status: ACTIVE**
A customer's current explicit statement takes priority over older memory. Memory provides context but does not override current facts.

### ACT-089 — Memory Deletion Request
**Status: ACTIVE**
Support customer requests to remove memory according to policy:
identify → permission/policy check → delete/anonymize/retain where legally required → audit.
The system must not claim deletion unless the data was actually handled accordingly.

### ACT-090 — Prompt Injection Defense
**Status: ACTIVE**
Customer messages are untrusted input. They cannot override system policy, tenant isolation, permissions, business rules, approval requirements, source-of-truth hierarchy or safety controls.
Defense must be layered, with authorization and access enforcement outside the LLM.

---

## LOCKED MASTER PRINCIPLES

1. DATABASE = FACTS
2. BUSINESS RULE ENGINE = DETERMINISTIC LOGIC
3. WORKFLOW ENGINE = PROCESS EXECUTION
4. EVENT BUS = SYSTEM COMMUNICATION
5. TASK SYSTEM = WORK MANAGEMENT
6. APPROVAL SYSTEM = HIGH-RISK DECISION CONTROL
7. AI = REASONING + LANGUAGE + ANALYSIS
8. OWNER AI = ORCHESTRATION + BUSINESS INTELLIGENCE
9. HUMAN OWNER = FINAL AUTHORITY
10. AI must not invent factual business data.
11. Critical actions must be deterministic/authorized outside the LLM.
12. Tenant isolation applies at every relevant layer.
13. Current official data overrides stale conversational assumptions.
14. Historical truth must remain auditable.
15. Important business-data changes use Change Requests and verification.
16. AI receives minimum necessary context.
17. Internal agent communication is structured, not unrestricted free-form reasoning.
18. Customer-facing responses are natural language, but must remain grounded.
19. High-risk actions require appropriate human approval.
20. Safety, authorization, auditability and tenant isolation take priority over AI convenience.

---

## STATUS

ACT-001 → ACT-090: **LOCKED**

Next decision batch: ACT-091 → ACT-100
Focus: Customer Conversation, Intent, Routing & Response.


---

## STAGE 6 — ORDER LIFECYCLE, CANCELLATION & REFUND

### ACT-101 — Order Start
**Status: ACTIVE**
Customer order begins with Intent → Product/Variant Validation → Stock Check → Cart → Customer Confirmation → Order. Cart, Order and Payment are separate concepts.

### ACT-102 — Cart Changes
**Status: ACTIVE**
Cart is mutable and changes are deterministically recalculated. Changing a cart item does not unnecessarily create a new order.

### ACT-103 — Checkout Pricing
**Status: ACTIVE**
At checkout, pricing is deterministically recalculated using the applicable official business rules. The resulting order stores an immutable price snapshot.

### ACT-104 — Stock at Checkout
**Status: ACTIVE**
A final transactional/atomic stock validation or reservation is required at checkout/commit. AI must not promise stock without authoritative validation.

### ACT-105 — Checkout Confirmation
**Status: ACTIVE**
Payment initiation requires explicit checkout confirmation according to the business flow. AI does not treat an unconfirmed cart as a final order/payment.

### ACT-106 — Pre-Payment Gate
**Status: ACTIVE**
Before payment initiation, validate cart, price, stock, customer/address where required, payment amount and order/payment state.

### ACT-107 — Payment Pending
**Status: ACTIVE**
A created payment request remains PAYMENT_PENDING until payment is verified. Only the payment gateway/verified webhook can establish PAID.

### ACT-108 — Transfer Proof
**Status: ACTIVE**
Customer-submitted transfer screenshots/proofs are not automatically verified payments. Verification must occur through the approved verification flow.

### ACT-109 — Duplicate Payment Webhooks
**Status: ACTIVE**
Payment/event processing must be idempotent and deduplicated. Duplicate success events cannot create duplicate orders, balance effects, subscriptions or fulfillment commands.

### ACT-110 — Payment Reconciliation
**Status: ACTIVE**
If payment succeeds externally but internal processing fails, the system must reconcile and recover idempotently. Customer must not be asked to pay again merely because internal processing failed.

## STAGE 6 — ORDER LIFECYCLE, CANCELLATION & REFUND

### ACT-111 — Order State Machine
**Status: ACTIVE**
Order lifecycle is deterministic, e.g. CART → PENDING_CONFIRMATION → ORDER_CREATED → PAYMENT_PENDING → PAID → PROCESSING → FULFILLED → COMPLETED, with controlled exception states such as CANCELLED, PAYMENT_FAILED, EXPIRED, REFUND_PENDING, REFUNDED, RETURN_REQUESTED, RETURNED and EXCHANGE_REQUESTED.

### ACT-112 — Order Cancellation
**Status: ACTIVE**
Cancellation is governed by order state, payment status, processing state, policy and actor authorization. AI interprets/coordinates but does not bypass policy.

### ACT-113 — Cancellation After Payment
**Status: ACTIVE**
Cancellation after payment is separate from refund. Eligibility and policy are checked before any refund workflow.

### ACT-114 — Refund Authority
**Status: ACTIVE**
Refund uses original payment/order data, official refund policy, eligibility and approved refund amount. AI cannot freely decide refund amounts.

### ACT-115 — Partial Refund
**Status: ACTIVE**
Partial refund amounts are calculated deterministically from official order/item/policy rules.

### ACT-116 — Refund Failure
**Status: ACTIVE**
A failed gateway refund is not marked REFUNDED. Use states such as REFUND_PENDING/REFUND_FAILED and reconciliation/retry workflows.

### ACT-117 — Return Eligibility
**Status: ACTIVE**
Return requests validate order, item, timing, fulfillment status, policy, reason and required evidence before creating a return workflow.

### ACT-118 — Exchange Validation
**Status: ACTIVE**
Exchange validates policy, order/item, requested variant, stock, item condition and applicable price/fee rules before execution.

### ACT-119 — Paid Order Exception
**Status: ACTIVE**
If payment is successful but stock/processing fails, use exception/reconciliation handling. Do not request duplicate payment. Available resolution options follow policy; refunds/compensation follow approval rules.

### ACT-120 — AI Recommendation vs Authority
**Status: ACTIVE**
When a customer says “decide for me,” AI may recommend the best permitted option, but recommendation does not equal authorization. Required approvals remain required.

## STAGE 7 — NOTIFICATION, FOLLOW-UP & HUMAN HANDOFF

### ACT-121 — Event vs Notification
**Status: ACTIVE**
EventBus records system facts/events. Notification is a separate communication action governed by notification policy.

### ACT-122 — Notification Policy
**Status: ACTIVE**
Notifications specify recipient, channel, priority, purpose, content/template, timing, permissions and delivery state. Events are not automatically broadcast to everyone.

### ACT-123 — Bounded Follow-Up
**Status: ACTIVE**
Follow-up uses bounded attempts, cooldowns and stop conditions. Repeated non-response transitions to appropriate WAITING_CLIENT/STALE handling rather than indefinite messaging.

### ACT-124 — Context-Aware Follow-Up
**Status: ACTIVE**
Follow-up considers conversation context, customer state, previous response, task, timing, preferences and business policy.

### ACT-125 — Communication Opt-Out
**Status: ACTIVE**
Requests not to receive proactive follow-up are enforced for relevant outbound communication. AI cannot create a workflow to circumvent the preference.

### ACT-126 — Inbound After Opt-Out
**Status: ACTIVE**
Opting out of proactive communication does not block the customer from initiating inbound conversations with the business.

### ACT-127 — Human Handoff Lifecycle
**Status: ACTIVE**
Human handoff is an explicit stateful process: AI_HANDOFF_REQUESTED → HUMAN_ASSIGNED → HUMAN_IN_PROGRESS → RESOLVED → VERIFY → RESUME_AI/CLOSE.

### ACT-128 — No Human Available
**Status: ACTIVE**
Use business hours, human availability, queue, priority and escalation policy. Critical cases may follow a different escalation path.

### ACT-129 — Human Takeover Lock
**Status: ACTIVE**
When a human takes over, AI auto-replies are paused according to policy. AI may provide internal assistance if permitted but must not conflict with the human.

### ACT-130 — Human-to-AI Handback
**Status: ACTIVE**
After human resolution, verify and update conversation/task/order state, create a structured summary, then resume AI with current context.

## STAGE 7 — WORKFLOW ENGINE & AUTOMATION

### ACT-131 — Stateful Workflow
**Status: ACTIVE**
Workflow is deterministic/stateful process execution: TRIGGER → CONDITION → ACTION → RESULT → NEXT STEP, with execution state/history.

### ACT-132 — AI Workflow Creation
**Status: ACTIVE**
Natural language may produce a structured workflow draft. Drafts require validation and authorization/activation according to risk.

### ACT-133 — Workflow Preview
**Status: ACTIVE**
Before activation, workflow preview/validation exposes trigger, conditions, actions, recipients, timing, frequency and limits as appropriate.

### ACT-134 — Workflow Duplicate Protection
**Status: ACTIVE**
Workflow identity, deduplication, idempotency and active-workflow detection prevent accidental duplicate execution.

### ACT-135 — Checkpointed Workflow Retry
**Status: ACTIVE**
Failed workflows resume from a safe checkpoint rather than blindly repeating already-committed actions.

### ACT-136 — Error-Aware Retry
**Status: ACTIVE**
Errors are classified (e.g. transient, permanent, data, permission, rate-limit, external failure, unknown) and each class gets an appropriate retry/escalation policy.

### ACT-137 — Retry Backoff
**Status: ACTIVE**
External/API retries use bounded exponential backoff with jitter where appropriate.

### ACT-138 — Workflow Timeout
**Status: ACTIVE**
Workflows/actions have appropriate timeouts and transition into recovery, retry or escalation instead of hanging indefinitely.

### ACT-139 — Loop Protection
**Status: ACTIVE**
Workflow execution has loop detection, execution-depth/count limits, event deduplication and emergency stop protections.

### ACT-140 — Workflow Cost Protection
**Status: ACTIVE**
Workflow execution is bounded by AI usage, API rate, execution and tenant-level cost/usage policies.

### ACT-141 — Execution-Time Permission
**Status: ACTIVE**
Permissions are enforced when a workflow executes, not only when it is created or activated.

### ACT-142 — Protected Data Mutation
**Status: ACTIVE**
Important business-data mutations remain subject to authorization, Change Request, approval, validation and audit requirements even when triggered by a workflow.

### ACT-143 — Scheduled Workflow
**Status: ACTIVE**
Scheduled workflows are timezone-aware and durable, with enabled state, entitlement/subscription checks, duplicate protection and relevant timing policies.

### ACT-144 — Missed Scheduled Run
**Status: ACTIVE**
After downtime, missed executions follow an explicit policy (execute, skip, reschedule or review) and remain idempotent.

### ACT-145 — Event vs Workflow
**Status: ACTIVE**
EventBus communicates facts; Workflow Engine executes processes triggered by those facts. Events do not contain unrestricted business-process logic.

### ACT-146 — Workflow Approval
**Status: ACTIVE**
Workflows can enter WAITING_APPROVAL and resume only after valid approval; rejection results in controlled termination/recovery.

### ACT-147 — Emergency Kill Switch
**Status: ACTIVE**
Human Owner can stop automation at appropriate scopes: tenant, workflow, outbound messaging, AI action, integration or feature. Kill switch has higher priority than normal workflow execution.

### ACT-148 — Safe Workflow Cancellation
**Status: ACTIVE**
Stopping a running workflow cancels future safe actions and reconciles state. Already committed actions are not falsely represented as undone.

### ACT-149 — Workflow Audit
**Status: ACTIVE**
Important executions record trigger, workflow/version, tenant, input/event, conditions, actions, results, errors, retries, approvals, final state and timestamps.

### ACT-150 — Workflow Versioning
**Status: ACTIVE**
Workflow versions are controlled. Existing executions retain their execution version while newly activated versions apply according to policy.

## STAGE 8 — EVENTBUS, TASK, APPROVAL & AGENT ORCHESTRATION

### ACT-151 — Event as System Fact
**Status: ACTIVE**
An event represents something that happened, not an unrestricted instruction to the system.

### ACT-152 — Event Metadata
**Status: ACTIVE**
Important events carry event_id, event_type, tenant_id, source, timestamp, payload, correlation_id, causation_id and schema_version as appropriate.

### ACT-153 — Event Idempotency
**Status: ACTIVE**
Event processing uses deduplication and idempotent consumers.

### ACT-154 — Event Ordering
**Status: ACTIVE**
Processing handles ordering/race conditions through state validation, ordering-aware mechanisms and reconciliation where needed.

### ACT-155 — Event Processing Failure
**Status: ACTIVE**
Events are not silently lost. Failed processing uses retry/backoff and eventually an error/dead-letter state with alert/escalation.

### ACT-156 — Event Schema Versioning
**Status: ACTIVE**
Event schemas are versioned with compatibility policy so evolution does not unexpectedly break consumers.

### ACT-157 — Workflow vs Task
**Status: ACTIVE**
Workflow = automated process. Task = work that an AI agent or human must perform. They are separate but integrated systems.

### ACT-158 — Structured Task
**Status: ACTIVE**
Tasks include assignee/agent/role, priority, objective, context, deadline where applicable, status, result and validation.

### ACT-159 — Task State Machine
**Status: ACTIVE**
Task lifecycle includes CREATED → ASSIGNED → IN_PROGRESS → WAITING_DATA/WAITING_APPROVAL → COMPLETED, with FAILED/BLOCKED/CANCELLED states.

### ACT-160 — Task Priority
**Status: ACTIVE**
Tasks have priority such as CRITICAL/HIGH/NORMAL/LOW. Priority affects scheduling/escalation but does not override authorization.

### ACT-161 — AI Task Creation
**Status: ACTIVE**
Owner AI may create structured tasks for specialist agents.

### ACT-162 — Agent-to-Agent Communication
**Status: ACTIVE**
Agent delegation uses structured contracts rather than unrestricted free-form agent chatter.

### ACT-163 — Independent Agent Authority
**Status: ACTIVE**
An agent cannot grant another agent authority it does not possess. Permissions, role, tenant, policy and approval remain independently enforced.

### ACT-164 — Delegation Limits
**Status: ACTIVE**
Delegation chains have depth, timeout, budget, permission, cancellation and audit controls.

### ACT-165 — Evidence-Backed Agent Results
**Status: ACTIVE**
Agent results should include evidence/source/calculation and confidence/validation where relevant. Downstream orchestration validates the result against the task objective.

### ACT-166 — Approval Object
**Status: ACTIVE**
Approval records action, target, reason, risk, evidence, requester, status, timestamp and result as applicable. States include PENDING, APPROVED, REJECTED, EXPIRED and CANCELLED.

### ACT-167 — Trusted Approval
**Status: ACTIVE**
AI cannot claim owner approval without a valid authorization/approval record from an authorized actor.

### ACT-168 — Bound Approval
**Status: ACTIVE**
Approval is time- and action-bound, including target and critical parameters such as amount where applicable. Expired or mismatched approvals cannot be reused.

### ACT-169 — Prioritized Owner AI Orchestration
**Status: ACTIVE**
When multiple problems exist, Owner AI assesses severity/impact, prioritizes, delegates, monitors and reports rather than creating uncontrolled task floods.

### ACT-170 — Closed-Loop Orchestration
**Status: ACTIVE**
Owner AI validates delegated results against objectives and evidence, determines outcome, takes/requests next action, records audit/memory and reports. Failed objectives trigger retry, revision, re-delegation or escalation.

---

## LOCKED STATUS

ACT-001 → ACT-170: **LOCKED**


---

## STAGE 9 — OWNER AI INTELLIGENCE & BUSINESS MEMORY

### ACT-171 — Data → Analysis → Insight
**Status: ACTIVE**
Owner AI explicitly separates Data, Analysis and Insight. Data states what happened; Analysis interprets/comparisons it; Insight identifies meaningful conclusions.

### ACT-172 — Insight → Recommendation
**Status: ACTIVE**
Recommendations are based on insight and include reason/evidence plus expected impact, relevant confidence, risk and alternatives where appropriate.

### ACT-173 — Recommendation ≠ Action
**Status: ACTIVE**
An Owner AI recommendation does not itself mutate business data or execute a consequential action. Important changes follow decision/approval → Change Request → validation → execution → verification.

### ACT-174 — Risk-Based Owner AI Authority
**Status: ACTIVE**
Owner AI authority is risk-based:
LOW may be automatic;
MEDIUM follows confirmation/policy;
HIGH requires approval;
CRITICAL requires explicit Human Owner approval.

### ACT-175 — Proactive Owner AI
**Status: ACTIVE**
Owner AI may detect, analyze, assess, recommend, create tasks, delegate, monitor, verify and report significant issues, subject to permissions and approval controls.

### ACT-176 — Bounded Proactivity
**Status: ACTIVE**
Owner AI is proactive but bounded by severity, impact, urgency, novelty, confidence and deduplication so the Owner is not overwhelmed by low-value alerts.

### ACT-177 — Daily Brief
**Status: ACTIVE**
Owner AI can provide a prioritized Daily Brief covering relevant revenue, sales, customers, orders, problems, AI usage/costs, important events, recommendations and pending decisions.

### ACT-178 — Weekly Business Review
**Status: ACTIVE**
Weekly Review provides strategic trends/comparisons across revenue, sales, conversion, customers, churn, operations, AI cost, opportunities, risks and recommendations rather than merely repeating the Daily Brief.

### ACT-179 — Forecast Is Not Fact
**Status: ACTIVE**
Forecasts/estimates/scenarios are explicitly distinguished from actual facts and should expose methodology/model, historical basis and assumptions/uncertainty where relevant.

### ACT-180 — Anomaly Validation
**Status: ACTIVE**
Anomaly detection is not proof of a problem. Owner AI validates against baseline/context, assesses significance and explains possible causes before recommending action.

### ACT-181 — Evidence-Backed Recommendation
**Status: ACTIVE**
A recommendation object should answer what is recommended, why, evidence, expected impact, risk, alternatives and suggested action as appropriate.

### ACT-182 — Recommendation History
**Status: ACTIVE**
Recommendations remain traceable through Owner decision → action → result → evaluation, forming part of the business feedback loop.

### ACT-183 — Rejected Recommendations
**Status: ACTIVE**
Relevant Owner rejections are remembered. Owner AI should suppress repetitive recommendations unless meaningful new evidence or circumstances justify revisiting them.

### ACT-184 — Recommendation vs Final Decision
**Status: ACTIVE**
If Owner modifies an AI recommendation, the original recommendation and final Owner decision are stored separately, with resulting action/outcome.

### ACT-185 — Structured Business Memory
**Status: ACTIVE**
Business Memory stores structured business context such as Owner decisions, policies, strategies, preferences, constraints and recurring instructions. It is not merely a transcript archive.

### ACT-186 — Memory Confidence
**Status: ACTIVE**
Memory records carry provenance/source, confidence, status, timestamp and scope where appropriate. Explicit Owner statements are stronger than AI-inferred assumptions.

### ACT-187 — Memory Conflict
**Status: ACTIVE**
Conflicting memories are resolved by scope/current validity and versioning. New scoped instructions can supersede older ones without destroying historical context.

### ACT-188 — Memory Scope Isolation
**Status: ACTIVE**
Memory is scoped as appropriate, including Global Owner, Business/Tenant, Channel, Customer, Project, Workflow or Task. Memory must not leak across isolated businesses.

### ACT-189 — Learning from Outcomes
**Status: ACTIVE**
Owner AI may learn from historical outcomes as evidence for future recommendations, but historical patterns cannot silently mutate official policies or business rules.

### ACT-190 — Uncertainty-Aware Owner AI
**Status: ACTIVE**
When data is insufficient, Owner AI must not invent an answer. It may retrieve authorized data, request missing information, create a task, request a decision, or provide clearly labeled scenarios/assumptions.

---

## LOCKED STATUS

ACT-001 → ACT-190: **LOCKED**


---

## STAGE 10 — PLATFORM HEALTH, OBSERVABILITY & INCIDENT MANAGEMENT

### ACT-191 — Component Health
**Status: ACTIVE**
The platform monitors critical components such as API, database, queue/cache where used, AI Gateway, WhatsApp integration and external integrations. Health states distinguish HEALTHY, DEGRADED and UNHEALTHY.

### ACT-192 — Lightweight Health Monitoring
**Status: ACTIVE**
Health checks use lightweight checks, timeouts, appropriate frequency and caching where suitable so monitoring does not itself overload the platform.

### ACT-193 — Structured Application Errors
**Status: ACTIVE**
Application errors such as HTTP 500, database errors, AI timeouts and webhook failures are structured, categorized, correlation-aware, tenant-aware where relevant, traceable and free of secret leakage.

### ACT-194 — Secure Structured Logging
**Status: ACTIVE**
Logs include appropriate timestamp, level, module/service, tenant context, request/correlation information, actor/event/error context as permitted. Secrets, tokens, passwords and unnecessary sensitive data are excluded.

### ACT-195 — Tenant-Scoped Observability
**Status: ACTIVE**
Platform operators/Owner AI may access cross-tenant operational information only within their authority. Tenant-level users cannot access another tenant's logs/observability data.

### ACT-196 — Error Spike Detection
**Status: ACTIVE**
The platform detects abnormal error-rate increases and can create incident candidates instead of waiting for customer complaints.

### ACT-197 — Incident vs Error
**Status: ACTIVE**
A single error is not automatically an incident. Incident severity is based on impact and scope, with levels such as LOW, MEDIUM, HIGH and CRITICAL.

### ACT-198 — Incident Lifecycle
**Status: ACTIVE**
Standard incident lifecycle:
DETECT → CONTAIN → DIAGNOSE → RECOVER → VERIFY → REPORT.

### ACT-199 — Bounded Automated Containment
**Status: ACTIVE**
For serious incidents, the system may perform safe, pre-authorized containment such as disabling a malfunctioning workflow. Containment remains within authority limits.

### ACT-200 — AI Support as Incident Analyst
**Status: ACTIVE**
AI Support may inspect errors, patterns, logs, metrics, recent changes, workflows, diagnose, create tasks and recommend recovery. Production-critical mutation remains subject to permission/approval.

### ACT-201 — Evidence-Based Diagnosis
**Status: ACTIVE**
Incident diagnosis must use evidence such as logs, metrics, traces, deployments, configuration changes, failed requests, affected workflows and historical incidents where available.

### ACT-202 — Root Cause vs Symptom
**Status: ACTIVE**
AI Support distinguishes symptom, probable cause and confirmed cause. A visible failure is not automatically the root cause.

### ACT-203 — Diagnosis Confidence
**Status: ACTIVE**
Unconfirmed diagnosis is represented as hypothesis with appropriate confidence/evidence. CONFIRMED status requires verification.

### ACT-204 — Deployment Correlation
**Status: ACTIVE**
Recent deployments can be correlated with incident timing as evidence, but temporal correlation is not treated as proof without verification.

### ACT-205 — Risk-Based Rollback
**Status: ACTIVE**
Rollback is a recovery option governed by risk policy. Some cases may permit automatic rollback; higher-risk cases require approval/manual intervention.

### ACT-206 — Verified Backup
**Status: ACTIVE**
Backups have schedule, retention, encryption/protection, verification, monitoring and restore procedures. A backup is not considered reliable merely because it was created; restore testing is required.

### ACT-207 — Disaster Recovery
**Status: ACTIVE**
DR has defined RPO/RTO and recovery procedures/strategies, with requirements potentially varying by plan.

### ACT-208 — Recovery Verification
**Status: ACTIVE**
A recovered server is not automatically considered healthy. Post-recovery verification checks critical database, API, integrations, workflows, queues, WhatsApp and business flows.

### ACT-209 — Audience-Aware Incident Communication
**Status: ACTIVE**
Incident communication is tailored to Customer, Client Owner and Internal Platform Team. Customer-facing messages contain relevant impact/status/solution, not raw technical stack traces.

### ACT-210 — Post-Incident Learning
**Status: ACTIVE**
Completed incidents produce a review covering root cause, impact, timeline, recovery, failures, protections, corrective/preventive actions and resulting improvements such as tests, monitoring, workflows and engineering tasks.

---

## LOCKED STATUS

ACT-001 → ACT-210: **LOCKED**


---

## STAGE 11 — SECURITY, AUTHENTICATION, AUTHORIZATION & TENANT ISOLATION

### ACT-211 — Authentication vs Authorization
**Status: ACTIVE**
Authentication establishes who the actor is; authorization determines what that actor may do. Successful login does not grant unrestricted access.

### ACT-212 — Trusted Tenant Context
**Status: ACTIVE**
Tenant context is not authentication. Production authorization derives tenant scope from a trusted authenticated/authorized actor context, not merely a client-supplied tenant identifier.

### ACT-213 — Client Headers Are Not Authority
**Status: ACTIVE**
Client-supplied tenant/actor role/permission/authentication headers are never accepted as authorization authority. They may be context hints only where appropriate; server-side trusted context must establish authority.

### ACT-214 — Missing Authentication Fails Closed
**Status: ACTIVE**
If an actor cannot be trusted/identified, access is denied. There is no fallback such as “first user = Owner.”

### ACT-215 — Strict Cross-Tenant Isolation
**Status: ACTIVE**
An actor attempting unauthorized access to another tenant is denied. Tenant scope is checked before data access or mutation.

### ACT-216 — Database Tenant Isolation
**Status: ACTIVE**
Tenant isolation is enforced beyond the API layer, including repository/service/database query boundaries. Explicit cross-tenant Owner AI analytics uses a validated elevated scope.

### ACT-217 — Cache Tenant Isolation
**Status: ACTIVE**
Cache keys and retrieval mechanisms are tenant-scoped so cached data cannot cross tenant boundaries.

### ACT-218 — Memory Tenant Isolation
**Status: ACTIVE**
Conversation context, business memory, customer memory, cached context, embeddings/retrieval and summaries must remain tenant-isolated.

### ACT-219 — AI Context Tenant Isolation
**Status: ACTIVE**
Before context reaches the AI Gateway/model, tenant authorization, data filtering and permission filtering are applied. The LLM is never relied upon to enforce tenant isolation.

### ACT-220 — Owner AI Cross-Tenant Analytics
**Status: ACTIVE**
Owner AI may compare multiple businesses only when the Human Owner is authorized for those tenant scopes. Access is explicit and purpose-limited, not unrestricted raw database access.

### ACT-221 — Human Admin Least Privilege
**Status: ACTIVE**
Human Admin access is restricted to authorized tenant scopes and assigned permissions. Admin authority does not automatically equal Owner authority.

### ACT-222 — Service-Layer Authorization
**Status: ACTIVE**
Authorization is enforced at the service/domain layer as well as API/router boundaries so workflows, agents, internal callers and alternate APIs cannot bypass security.

### ACT-223 — Trusted Internal Calls
**Status: ACTIVE**
Internal service-to-service calls are not inherently trusted. They carry an explicit trusted actor/service context and respect permission boundaries. Any internal bypass is explicit, limited and controlled.

### ACT-224 — Secret Isolation
**Status: ACTIVE**
API keys, database credentials, webhook secrets, encryption keys and tokens are excluded from prompts, customer messages, logs, analytics, ordinary records and source repositories.

### ACT-225 — AI Secret Isolation
**Status: ACTIVE**
AI agents operate through protected capabilities/tools and do not receive raw credentials merely to diagnose or operate an integration.

### ACT-226 — Strong API Authentication
**Status: ACTIVE**
Production APIs require strong authentication with appropriate expiration/revocation/session controls and secure transport. Tenant headers are not a substitute for authentication.

### ACT-227 — Verified Webhooks
**Status: ACTIVE**
Machine-to-machine webhooks use provider-appropriate verification such as signature/HMAC/verification tokens. Knowledge of an endpoint URL alone does not establish authenticity.

### ACT-228 — Replay Protection
**Status: ACTIVE**
Webhook/payment processing uses available event/request identifiers, timestamp windows where supported, signature verification, idempotency and deduplication to mitigate replay/duplicate processing.

### ACT-229 — Rate Limiting & Abuse Protection
**Status: ACTIVE**
Layered protection covers brute force, spam, excessive AI calls, webhook abuse, repeated authentication failures and workflow abuse, with limits appropriate to IP, actor, tenant, endpoint, integration and plan/usage where relevant.

### ACT-230 — Security Incident Lifecycle
**Status: ACTIVE**
Potential cross-tenant access, credential leakage, unauthorized actions, suspicious authentication or webhook abuse enters the security incident lifecycle:
DETECT → CONTAIN → DIAGNOSE → RECOVER → VERIFY → REPORT.

---

## LOCKED STATUS

ACT-001 → ACT-230: **LOCKED**


---

## STAGE 12 — BILLING, SUBSCRIPTION, ENTITLEMENT, USAGE & AI COST

### ACT-231 — Subscription vs Operational Status
**Status: ACTIVE**
Subscription state and bot/system operational status are separate state domains and may legitimately differ.

### ACT-232 — Subscription State Machine
**Status: ACTIVE**
Subscription uses deterministic states such as ACTIVE, PAYMENT_PENDING, GRACE, RESTRICTED, SUSPENDED, EXPIRED and ARCHIVED. Billing rules, not AI judgment, control state transitions.

### ACT-233 — Trial Lifecycle
**Status: ACTIVE**
The default trial is 7 days. Trial expiry follows billing policy and may transition to payment/grace/restricted states. AI cannot self-extend a trial.

### ACT-234 — Grace Period
**Status: ACTIVE**
Failed payment can enter a controlled GRACE period before restriction/suspension. Duration and capability restrictions follow billing policy.

### ACT-235 — Restricted Subscription
**Status: ACTIVE**
Restriction is entitlement-driven. Individual capabilities may remain available while others are limited/disabled. Onboarding data is preserved.

### ACT-236 — Expired Subscription
**Status: ACTIVE**
Expiry disables capabilities according to policy, preserves data according to retention rules, and does not automatically delete the tenant. Reactivation is policy-controlled.

### ACT-237 — Upgrade
**Status: ACTIVE**
Plan upgrade follows eligibility → current price/terms → confirmation → payment → verified payment → entitlement update → verification. AI cannot directly mutate the billing plan.

### ACT-238 — Downgrade Impact Analysis
**Status: ACTIVE**
Downgrades evaluate feature/usage impact before applying the new entitlement. Excess workflows/data/capabilities are not silently deleted.

### ACT-239 — Downgrade Data Preservation
**Status: ACTIVE**
Data that becomes unavailable after downgrade is preserved but restricted when policy permits, allowing potential restoration after upgrade within retention limits.

### ACT-240 — Central Entitlement Engine
**Status: ACTIVE**
Effective entitlement is deterministically calculated from applicable plan, add-ons, subscription state and usage/policy:
Plan + Add-ons + Subscription Status + Usage Policy → Effective Entitlements.

### ACT-241 — Add-On Entitlement
**Status: ACTIVE**
Add-ons are explicit billable/entitlement objects with status, pricing/billing period and expiration where applicable. Effective features combine base plan and active add-ons.

### ACT-242 — Granular AI Usage
**Status: ACTIVE**
AI usage records include tenant, agent, model, task, feature/request, timestamp and available usage/token/cost metrics.

### ACT-243 — AI Cost Attribution
**Status: ACTIVE**
AI cost is attributable to tenant and relevant agent/task/model/execution where possible, rather than only as an undifferentiated provider total.

### ACT-244 — Usage Thresholds
**Status: ACTIVE**
Default AI usage thresholds are 70% warning, 85% strong warning/economy-mode consideration and 100% limit/restriction, subject to plan policy.

### ACT-245 — Economy Mode
**Status: ACTIVE**
Economy Mode can reduce AI cost through approved measures such as cheaper capability/model selection, context reduction, lower frequency or delaying non-critical automation. Critical business behavior is not silently altered.

### ACT-246 — Usage Limit/Overage Policy
**Status: ACTIVE**
When limits are reached, the platform follows an explicit policy such as restriction, degradation, top-up, upgrade or permitted overage. Unlimited negative billing is not created silently.

### ACT-247 — AI Cost Anomaly
**Status: ACTIVE**
Large unexpected AI-cost increases are detected as anomalies. Owner AI can explain likely drivers and recommend bounded containment.

### ACT-248 — Tenant AI Budget
**Status: ACTIVE**
Tenants may have budgets with current spend, projected spend, remaining budget and expected usage. Budget enforcement remains deterministic.

### ACT-249 — Billing Conflict Reconciliation
**Status: ACTIVE**
Conflicting billing/subscription states are not resolved by AI guesswork. The system identifies the billing source of truth, reconciles state, corrects records and audits the change.

### ACT-250 — Payment/Subscription Recovery
**Status: ACTIVE**
If verified payment succeeds but subscription activation fails internally, idempotent reconciliation restores the correct subscription/entitlement state without requiring duplicate payment.

---

## LOCKED STATUS

ACT-001 → ACT-250: **LOCKED**


---

## STAGE 13 — CLIENT ONBOARDING, PROVISIONING, CONFIGURATION & ACTIVATION

### ACT-251 — Provisioning vs Coding
**Status: ACTIVE**
Provisioning configures a tenant on the Universal Core. It does not create separate source code per client.

### ACT-252 — Idempotent Provisioning
**Status: ACTIVE**
Repeated provisioning attempts must not create duplicate tenants, subscriptions, workflows, integrations or configuration.

### ACT-253 — Partial Provisioning
**Status: ACTIVE**
Provisioning is dependency-aware. A failed capability does not automatically invalidate unrelated completed capabilities.

### ACT-254 — Requirement Engine
**Status: ACTIVE**
Requirement Engine determines onboarding requirements from plan, business type, enabled features, integrations, existing data and missing data, producing an actionable onboarding plan/checklist.

### ACT-255 — Incremental Requirement Recalculation
**Status: ACTIVE**
Changes in business type/features/requirements trigger incremental recalculation without unnecessarily destroying valid progress.

### ACT-256 — Actual Requirement Progress
**Status: ACTIVE**
Onboarding progress reflects actual applicable requirements and capability readiness, not merely completed forms.

### ACT-257 — Requirement Priority
**Status: ACTIVE**
Requirements have priority/severity such as REQUIRED, IMPORTANT and OPTIONAL, so missing data is handled according to business impact.

### ACT-258 — Progressive Onboarding
**Status: ACTIVE**
Incomplete data does not force the entire onboarding process to stop. Valid progress is preserved and independent work can continue.

### ACT-259 — AI-Assisted Data Extraction
**Status: ACTIVE**
AI may extract/structure client-provided information into drafts. Validation and official-data rules still apply before activation.

### ACT-260 — No Invented Business Data
**Status: ACTIVE**
AI cannot create factual business values that the client/system did not provide or authorize.

### ACT-261 — Configuration Preview
**Status: ACTIVE**
Before activation, clients can review applicable business profile, products, policies, AI behavior, automation, integrations and permissions/configuration.

### ACT-262 — Structured AI Behavior Configuration
**Status: ACTIVE**
Natural-language AI behavior requests become structured drafts → validation → permission/entitlement check → client confirmation → active configuration.

### ACT-263 — Configuration Conflict Detection
**Status: ACTIVE**
Conflicting active rules/configurations must be detected and resolved before they create ambiguous behavior.

### ACT-264 — Capability Dependency Graph
**Status: ACTIVE**
Capabilities have explicit dependencies. A blocked dependency only blocks capabilities that actually depend on it; independent onboarding work may continue.

### ACT-265 — Automated AI Testing
**Status: ACTIVE**
Pre-activation tests cover representative factual retrieval, stock, FAQ, order, handoff, unknown-question and prompt-injection scenarios as applicable.

### ACT-266 — Evidence-Based Readiness
**Status: ACTIVE**
A failed test is categorized, analyzed, safely fixed or delegated where possible, retested and reflected in the readiness gate. Failed critical tests prevent false READY status.

### ACT-267 — Client Acceptance Testing
**Status: ACTIVE**
Client acceptance testing is part of readiness evidence after automated tests, where the capability/process requires client validation.

### ACT-268 — Capability-Level Activation
**Status: ACTIVE**
Where dependencies allow, ready capabilities may activate while unready capabilities remain disabled/pending. Client is informed of limitations.

### ACT-269 — Pause/Resume Onboarding
**Status: ACTIVE**
PAUSED preserves validated progress, stops active reminders according to policy, keeps subscription state separate and resumes from the preserved point.

### ACT-270 — Final Activation Gate
**Status: ACTIVE**
Activation requires applicable subscription/entitlement validity, required data, required integrations, security checks, automated tests and required client acceptance/approval. READY → ACTIVE is followed by post-activation verification and an activation report.

---

## LOCKED STATUS

ACT-001 → ACT-270: **LOCKED**


---

## STAGE 14 — INTEGRATIONS, WHATSAPP & EXTERNAL SYSTEMS

### ACT-271 — Integration as Capability
**Status: ACTIVE**
External integrations are standardized capability objects containing provider, tenant, status, permissions, credential reference, capabilities, health and lifecycle information.

### ACT-272 — Integration Lifecycle
**Status: ACTIVE**
Integrations use a deterministic lifecycle such as DISCOVERED → CONFIGURING → CONNECTING → CONNECTED → VERIFYING → ACTIVE, with controlled exception states FAILED, EXPIRED, DISCONNECTED and SUSPENDED/REVOKED.

### ACT-273 — Credential Isolation
**Status: ACTIVE**
Integration credentials are isolated from AI prompts, customer-visible responses and logs. Persistent secrets use protected/encrypted storage or secure secret references with least-privilege access.

### ACT-274 — WhatsApp Channel Identity
**Status: ACTIVE**
Each WhatsApp number has an isolated channel identity, including tenant, phone identity, permissions, routing, workflows, status and configuration.

### ACT-275 — WhatsApp Webhook Verification
**Status: ACTIVE**
Incoming WhatsApp webhooks must pass source/signature validation, event validation, tenant/channel mapping and replay protection before business logic processing.

### ACT-276 — WhatsApp Event Idempotency
**Status: ACTIVE**
Repeated provider events must be deduplicated using provider event identity and channel/context so one external event cannot create duplicate business actions.

### ACT-277 — WhatsApp Outbound Delivery State
**Status: ACTIVE**
Outbound messages use explicit delivery states such as CREATED → QUEUED → SENT → DELIVERED → READ, with controlled FAILED/EXPIRED/CANCELLED states.

### ACT-278 — WhatsApp Outbound Rate Protection
**Status: ACTIVE**
Outbound messaging uses queueing, rate limits, bounded retries, exponential backoff/jitter, priority, cooldown and dead-letter handling to prevent uncontrolled provider requests.

### ACT-279 — WhatsApp Disconnect Recovery
**Status: ACTIVE**
A disconnected WhatsApp channel transitions to a controlled degraded state, pauses dependent actions, preserves data, supports reconnect and verifies the channel before returning to active operation.

### ACT-280 — Multi-WhatsApp Tenant Isolation
**Status: ACTIVE**
A tenant may have multiple WhatsApp numbers. Each channel can have independent role, routing, workflow, escalation, AI capability and context while remaining isolated from other channels unless explicitly shared.

### ACT-281 — Deterministic Calendar Operations
**Status: ACTIVE**
Calendar AI may interpret customer intent, but availability, booking, cancellation and rescheduling are executed against the authoritative calendar/system state.

### ACT-282 — Calendar Commit Recheck
**Status: ACTIVE**
Calendar availability must be rechecked at booking commit time. A race/conflict cannot be overridden by AI; the system must reconcile and offer an alternative where appropriate.

### ACT-283 — Explicit Google Sheets Source of Truth
**Status: ACTIVE**
Google Sheets can serve as import, export, operational or reporting data depending on configuration. It is not automatically authoritative; source-of-truth authority is defined per data domain/type.

### ACT-284 — Controlled Spreadsheet Sync
**Status: ACTIVE**
Spreadsheet synchronization requires explicit direction, mapping, trigger/schedule, version/timestamp, conflict strategy, error handling and audit behavior.

### ACT-285 — Spreadsheet Conflict Resolution
**Status: ACTIVE**
Conflicts between system data and spreadsheet data are resolved deterministically using configured source priority/version/timestamp and Change Request or confirmation when required. AI does not guess the correct value.

### ACT-286 — Payment Gateway Verification
**Status: ACTIVE**
Payment status is verified through the authoritative payment gateway/webhook flow with signature verification, idempotency and reconciliation. Customer claims or screenshots are not payment authority.

### ACT-287 — Standardized External API Failure Handling
**Status: ACTIVE**
External API failures are classified and handled through safe retry, backoff, fallback where available, state preservation and escalation/alerting when materially impactful.

### ACT-288 — Credential Expiry and Revocation
**Status: ACTIVE**
Expired or revoked credentials transition integrations to a reauthentication-required/degraded state. The system stops unsafe repeated requests and preserves configuration/data during reauthentication.

### ACT-289 — Integration Health
**Status: ACTIVE**
Each integration exposes HEALTHY, DEGRADED or UNHEALTHY status based on connectivity, authentication, provider status, recent failures, latency and capability-specific checks.

### ACT-290 — Deterministic Integration Reconciliation
**Status: ACTIVE**
When internal and external states differ, the system detects the mismatch, determines authoritative source, reconciles deterministically, updates state, audits the result and verifies recovery. AI does not guess final transactional state.

---

## LOCKED STATUS

ACT-001 → ACT-290: **LOCKED**


---

## STAGE 15 — CUSTOMER, CRM, MEMORY & CONVERSATION INTELLIGENCE

### ACT-291 — Canonical Customer Identity
**Status: DEFERRED**
Each customer has a stable internal Customer ID. WhatsApp numbers and other contact methods are contact identities, not the sole customer identity.

### ACT-292 — Prospect, Lead, Customer and Client Separation
**Status: DEFERRED**
Prospect/Lead, Customer and Client/Tenant are distinct business entities/lifecycle concepts and must not be conflated.

### ACT-293 — Structured Customer Profile
**Status: DEFERRED**
Customer Profile stores structured facts and relevant metadata separately from raw conversation history.

### ACT-294 — Selective Customer Memory
**Status: DEFERRED**
Customer Memory stores only relevant, useful, scoped information with provenance, confidence and timestamps rather than every conversational statement.

### ACT-295 — AI Memory Candidate Validation
**Status: DEFERRED**
AI may extract candidate memories, but candidates require validation/confidence handling before becoming usable stored memory.

### ACT-296 — Explicit Information Priority
**Status: DEFERRED**
Explicit, current customer statements have higher authority than AI inference when determining customer memory.

### ACT-297 — Memory Confidence and Status
**Status: DEFERRED**
Memory carries confidence/status such as CONFIRMED, LIKELY, INFERRED, STALE and CONFLICTED. Low-confidence memory cannot drive sensitive decisions.

### ACT-298 — Conflict-Aware Memory
**Status: DEFERRED**
When current customer information conflicts with old memory, current validated information becomes current memory while relevant historical changes may be retained.

### ACT-299 — Time-Aware Memory
**Status: DEFERRED**
Memory can have freshness, expiry or review rules. Temporary circumstances must not automatically become permanent preferences.

### ACT-300 — Sensitive Memory Protection
**Status: DEFERRED**
Sensitive customer information requires purpose, permission, policy and retention controls before being stored or used as memory.

### ACT-301 — Conversation Summary plus Raw History
**Status: DEFERRED**
Long conversations may produce structured summaries containing goal, important facts, products/orders, pending actions and next steps. Summaries complement rather than replace raw history.

### ACT-302 — Event-Backed Customer Timeline
**Status: DEFERRED**
Customer timelines are built primarily from system/event data, with AI interpretation used as a supporting layer rather than factual authority.

### ACT-303 — Explainable Customer Segmentation
**Status: DEFERRED**
Customer segments may use deterministic business rules and analytical recommendations. Segment criteria must remain configurable and explainable.

### ACT-304 — Explainable Customer Scoring
**Status: DEFERRED**
Customer scores must expose basis/formula or model, evidence, timestamp and confidence so they can support sales, retention and engagement decisions without pretending to be absolute facts.

### ACT-305 — Intent Detection with Deterministic Routing
**Status: DEFERRED**
AI may classify customer intent, but intent is interpretation rather than authorization. Actions are routed through deterministic rules, permissions and business engines.

### ACT-306 — Context Assembly Service
**Status: DEFERRED**
AI context is assembled from current message, recent conversation, summary, relevant customer memory/state, relevant business data/knowledge and current task, filtered by permission, relevance and token budget.

### ACT-307 — Relevant Cross-Conversation Memory
**Status: DEFERRED**
Related customer conversations may be linked when identity and tenant scope match, but only relevant context is retrieved into a new interaction.

### ACT-308 — Policy-Driven Customer Data Deletion
**Status: DEFERRED**
Customer deletion/forget requests follow identify → determine applicable data → delete/anonymize/legally-required retention → applicable memory removal → audit.

### ACT-309 — Personalization Guard
**Status: DEFERRED**
Customer memory may personalize communication but cannot override current transactional/business authority such as price, stock, payment, order or policy.

### ACT-310 — Learning without Autonomous Policy Mutation
**Status: DEFERRED**
AI may learn from outcomes and recommendations, but observed patterns cannot autonomously change official business policies or rules. Policy changes require the established authorization/change process.

---

## LOCKED STATUS

ACT-001 → ACT-310: **LOCKED**


---

## STAGE 16 — SALES, LEADS, CRM & CUSTOMER JOURNEY

### ACT-311 — Deterministic Sales Lifecycle
**Status: DEFERRED**
Sales lifecycle follows PROSPECT → LEAD → QUALIFIED → PROPOSAL → WAITING_PAYMENT → PAID, followed by explicit handoff to Client Manager/onboarding after verified payment.

### ACT-312 — Lead Identity and Deduplication
**Status: DEFERRED**
Lead identity uses tenant-scoped contact identities and matching rules. Possible duplicates are resolved according to confidence and human review when ambiguous.

### ACT-313 — Adaptive Lead Qualification
**Status: DEFERRED**
Sales AI qualifies needs, business type, pain points, required features, budget/timeline where relevant and decision context adaptively rather than forcing a fixed questionnaire.

### ACT-314 — Explainable Lead Scoring
**Status: DEFERRED**
Lead score may use engagement, business fit, need, buying intent, timeline and interaction history, with evidence and timestamp.

### ACT-315 — System-Based Package Recommendation
**Status: DEFERRED**
Sales AI may recommend plans/packages based on detected needs, while price, features, entitlements and promotions come from authoritative system data.

### ACT-316 — Ethical Sales Guardrails
**Status: DEFERRED**
Sales AI cannot fabricate urgency, promotions, testimonials or capabilities, pressure customers deceptively, conceal material limitations or promise authority outside configured entitlement.

### ACT-317 — AI Proposal Drafting
**Status: DEFERRED**
AI may generate proposal drafts from official package, need, feature, price, add-on and period data. Required approvals must occur before binding/active proposal use.

### ACT-318 — Immutable Proposal Versioning
**Status: DEFERRED**
Proposal changes create versions. Prior versions remain available for audit and historical reference.

### ACT-319 — Deterministic Discount Authority
**Status: DEFERRED**
Discount authority is determined by configured thresholds/permissions. AI cannot exceed its authorized discount level without the required confirmation or Owner approval.

### ACT-320 — Controlled Negotiation
**Status: DEFERRED**
Negotiation requests may produce official alternatives or approval requests, but AI cannot independently alter official pricing or commercial policy.

### ACT-321 — Stateful Follow-Up
**Status: DEFERRED**
Follow-up uses explicit states such as WAITING_CUSTOMER, FOLLOW_UP_DUE, CONTACTED, RESPONDED, NO_RESPONSE, BOUNDED_FOLLOW_UP and WAITING_CLIENT rather than unmanaged timers.

### ACT-322 — Follow-Up Cooldown and Bounds
**Status: DEFERRED**
Automated follow-up uses maximum attempts, cooldown, quiet hours, communication policy and stop conditions. No indefinite messaging.

### ACT-323 — Follow-Up Stop Conditions
**Status: DEFERRED**
Follow-up stops when the customer purchases, declines, opts out, hands off to human, becomes inactive/stale or enters a state incompatible with the workflow.

### ACT-324 — Inbound Customer Priority
**Status: DEFERRED**
A customer response takes priority over pending automated follow-up so automation does not continue as if no response occurred.

### ACT-325 — Sales Human Handoff
**Status: DEFERRED**
Sales handoff preserves customer profile, needs, conversation summary, proposal, objections, pending decisions and relevant history.

### ACT-326 — Evidence-Based Lost Lead Reason
**Status: DEFERRED**
Lost lead reasons may be recorded/classified from available evidence, but AI cannot invent a reason that the customer or system did not establish.

### ACT-327 — Bounded Win-Back Automation
**Status: DEFERRED**
Inactive leads/customers may enter policy-controlled win-back workflows with eligibility, personalization, bounded attempts, cooldown and opt-out enforcement.

### ACT-328 — Evidence-Based Retention Signals
**Status: DEFERRED**
Retention/churn signals may use engagement, transaction, complaint, usage, payment and support evidence. A signal is not treated as certainty.

### ACT-329 — Event-Backed Customer Journey
**Status: DEFERRED**
CRM journey milestones are backed by system/event data where possible, covering contact, qualification, proposal, payment, onboarding, activation, usage, support, renewal and expansion.

### ACT-330 — Sales-to-Operations Ownership Transfer
**Status: DEFERRED**
Verified payment triggers explicit ownership transfer from Sales to Client Manager/onboarding while preserving relevant sales context and history.

---

## LOCKED STATUS

ACT-001 → ACT-330: **LOCKED**


---

## STAGE 17 — MARKETING & AUTOMATION

### ACT-331 — Marketing AI Scope
**Status: DEFERRED**
Marketing AI supports campaign ideation, segmentation, copywriting, content planning, campaign analysis and recommendations, with risk-based limits on execution authority.

### ACT-332 — Marketing Data Source
**Status: DEFERRED**
Marketing recommendations use authoritative tenant business data such as customer segments, products, prices, promotions, inventory and campaign history.

### ACT-333 — Campaign Object
**Status: DEFERRED**
Campaigns are structured objects containing objective, audience, offer, channel, content, budget, schedule, status and results.

### ACT-334 — Campaign Lifecycle
**Status: DEFERRED**
Campaign lifecycle is deterministic: DRAFT → REVIEW → APPROVED → SCHEDULED → RUNNING → COMPLETED, with PAUSED/CANCELLED/FAILED exception states.

### ACT-335 — Marketing Approval
**Status: DEFERRED**
Paid campaigns and campaigns with material reputational/financial risk require approval according to configured authority.

### ACT-336 — Audience Eligibility
**Status: DEFERRED**
Before marketing send, the system checks segment eligibility, consent/opt-in, opt-out, frequency limits and campaign exclusions.

### ACT-337 — Promotion Truth
**Status: DEFERRED**
Marketing AI may only use promotions that are official, active, time-valid and applicable to the target audience.

### ACT-338 — Inventory-Aware Marketing
**Status: DEFERRED**
Product campaigns may check inventory and can be blocked, adjusted or sent for approval when inventory conditions make the campaign unsafe.

### ACT-339 — Campaign Budget
**Status: DEFERRED**
Campaigns have planned/actual spend, thresholds, approval authority and stop conditions. AI cannot exceed authorized budget.

### ACT-340 — Grounded Content Generation
**Status: DEFERRED**
AI-generated marketing content is grounded in approved business data and may produce captions, headlines, CTAs and channel-specific drafts.

### ACT-341 — Content Safety
**Status: DEFERRED**
Marketing AI cannot fabricate claims, misleading promises, unsupported testimonials or content that conflicts with approved business policy.

### ACT-342 — Permission-Aware Personalization
**Status: DEFERRED**
Marketing personalization may use authorized customer memory/segments only and must respect privacy, consent and scope.

### ACT-343 — Centralized Message Frequency
**Status: DEFERRED**
Marketing automation follows centralized message frequency caps, cooldowns and quiet-hour rules.

### ACT-344 — Marketing Opt-Out
**Status: DEFERRED**
Applicable marketing automation stops when a customer opts out. Opt-out does not prevent the customer from initiating inbound contact.

### ACT-345 — Controlled Marketing Experiments
**Status: DEFERRED**
A/B tests and experiments use explicit experiment IDs/versions and controlled comparison/evaluation.

### ACT-346 — Attribution with Uncertainty
**Status: DEFERRED**
Campaign attribution distinguishes delivery, engagement, conversion and attributed revenue, without assuming a campaign was the sole cause of revenue.

### ACT-347 — Marketing Analytics
**Status: DEFERRED**
Marketing analytics separates actual metrics from AI interpretation and follows Data → Analysis → Intelligence.

### ACT-348 — Deterministic Marketing Stop
**Status: DEFERRED**
Campaigns can be automatically stopped by budget thresholds, abuse, provider failure, invalid inventory/policy conditions or Owner kill switch.

### ACT-349 — Marketing Audit
**Status: DEFERRED**
Campaign creation, versions, approvals, targets, changes, execution, results and stop/cancellation reasons are auditable.

### ACT-350 — Marketing Feedback Loop
**Status: DEFERRED**
Campaign outcomes feed analysis and future recommendations but do not autonomously mutate official marketing policy.

---

## STAGE 18 — FINANCE & BUSINESS OPERATIONS

### ACT-351 — Finance AI Scope
**Status: DEFERRED**
Finance AI provides monitoring, categorization, reporting, cash-flow analysis, anomaly detection, forecasting and recommendations; it is not the accounting authority.

### ACT-352 — Financial Source of Truth
**Status: DEFERRED**
Financial facts originate from verified transactions, payment gateways, accounting/financial integrations and approved business records according to configured authority.

### ACT-353 — Financial Transaction Object
**Status: DEFERRED**
Financial transactions have tenant-scoped identity, date, amount, currency, type, source, status, reference and reconciliation state.

### ACT-354 — Explicit Financial Semantics
**Status: DEFERRED**
Order value, payment received, refund, revenue metrics and outstanding amounts are distinct financial concepts and must not be conflated.

### ACT-355 — Controlled Expense Tracking
**Status: DEFERRED**
Expenses can enter through authorized manual entry, integrations, imports or approved records. AI can assist but does not become the financial source of truth.

### ACT-356 — AI-Assisted Financial Categorization
**Status: DEFERRED**
AI may suggest financial categories with confidence. Low-confidence classifications enter review rather than becoming authoritative silently.

### ACT-357 — Deterministic Financial Reconciliation
**Status: DEFERRED**
Internal records are reconciled against gateways, banks or accounting systems using deterministic comparison and controlled resolution.

### ACT-358 — Actual vs Expected Cash Flow
**Status: DEFERRED**
Cash-flow reporting distinguishes actual inflow/outflow, pending amounts, expected amounts and forecasts.

### ACT-359 — Evidence-Based Cash-Flow Forecast
**Status: DEFERRED**
Cash-flow forecasts use historical/known financial data and explicit assumptions, methodology and confidence.

### ACT-360 — Financial Anomaly Detection
**Status: DEFERRED**
The system may flag abnormal transactions, expense spikes, revenue drops, payment mismatches or unusual refunds. An anomaly is not automatically fraud.

### ACT-361 — Fraud as Signal, Not Accusation
**Status: DEFERRED**
AI may identify potential suspicious activity but cannot assert fraud without authoritative evidence/determination.

### ACT-362 — Financial Approval
**Status: DEFERRED**
High-impact financial actions such as large refunds, payouts, adjustments, write-offs or compensation follow configured risk-based approval.

### ACT-363 — Financial Mutation Protection
**Status: DEFERRED**
AI cannot directly mutate authoritative financial transactions. Financial changes follow authorization → approval where required → deterministic execution → verification → audit.

### ACT-364 — Invoice Lifecycle
**Status: DEFERRED**
Invoices follow DRAFT → ISSUED → SENT → PAID, with OVERDUE/VOID/CANCELLED exception states and verified payment status.

### ACT-365 — Accounts Receivable Monitoring
**Status: DEFERRED**
The system tracks unpaid, overdue, pending and mismatched payments and applies communication policy to any follow-up.

### ACT-366 — Business KPI Registry
**Status: DEFERRED**
Owner AI can monitor revenue, orders, customers, conversion, retention, expenses, profit metrics, usage, support and operational health using versioned KPI definitions.

### ACT-367 — KPI Definition Change Control
**Status: DEFERRED**
AI cannot silently alter KPI definitions. Definition changes use Change Request → Review → Owner Approval → Version.

### ACT-368 — Business Decision Simulation
**Status: DEFERRED**
Owner AI can model business scenarios with explicit assumptions, methodology, uncertainty and projected impact, clearly separated from actual results.

### ACT-369 — Controlled Financial Period Close
**Status: DEFERRED**
Closed financial periods are protected from silent mutation. Adjustments use controlled adjustment procedures and audit trails.

### ACT-370 — Finance Feedback Loop
**Status: DEFERRED**
Financial intelligence follows Transaction → Reconciliation → Analysis → Insight → Recommendation → Owner Decision → Action → Result, without autonomous financial policy mutation.

---

## STAGE 19 — AI ANALYST, BI, FORECASTING & DECISION INTELLIGENCE

### ACT-371 — AI Analyst Role
**Status: DEFERRED**
AI Analyst transforms data into Analysis, Insight and Recommendation while remaining separate from Owner decision authority.

### ACT-372 — Actual vs Derived Data
**Status: DEFERRED**
Analytics distinguishes Actual, Calculated, Estimated, Forecast and AI Interpretation.

### ACT-373 — Metric Definition Registry
**Status: DEFERRED**
Important metrics have centralized name, definition, formula, source, scope, version, timezone and update frequency.

### ACT-374 — Centralized KPI Calculation
**Status: DEFERRED**
Core KPI calculations use a centralized metric engine so dashboards and AI produce consistent definitions.

### ACT-375 — Tenant Analytics Timezone
**Status: DEFERRED**
Analytics uses the configured tenant/business timezone while preserving original timestamps for traceability.

### ACT-376 — Deterministic Reporting Periods
**Status: DEFERRED**
Reports support standard and custom periods with deterministic timezone-aware boundaries.

### ACT-377 — Dashboard Facts vs AI Interpretation
**Status: DEFERRED**
Dashboards expose factual metrics; AI Analyst provides interpretation, explanation and recommendations separately.

### ACT-378 — Evidence-Based Trend Detection
**Status: DEFERRED**
Trend detection includes comparison periods and evidence rather than relying on isolated values.

### ACT-379 — Baseline-Aware Anomaly Detection
**Status: DEFERRED**
Anomalies are evaluated against an appropriate baseline such as historical behavior, seasonality or configured thresholds.

### ACT-380 — Seasonality-Aware Analysis
**Status: DEFERRED**
Where sufficient data exists, analysis may account for recurring day/week/month/season/campaign patterns.

### ACT-381 — Structured Forecast Object
**Status: DEFERRED**
Forecasts store metric, period, prediction/range, confidence, method, assumptions, creation time and model/version.

### ACT-382 — Forecast Is Not Fact
**Status: DEFERRED**
Forecast outputs must be explicitly labeled as predictions/estimates rather than actual business facts.

### ACT-383 — Forecast Uncertainty
**Status: DEFERRED**
Forecasts expose confidence/uncertainty and may return insufficient reliability when data quality is inadequate.

### ACT-384 — Forecast Data Quality Gate
**Status: DEFERRED**
Forecasting requires minimum data volume, completeness, consistency and freshness. Otherwise the result is INSUFFICIENT_DATA or equivalent.

### ACT-385 — Multi-Scenario Analysis
**Status: DEFERRED**
Owner AI can compare baseline, best-case, worst-case and custom scenarios with explicit assumptions.

### ACT-386 — Scenario Isolation
**Status: DEFERRED**
Simulations cannot mutate actual business records and use isolated scenario state.

### ACT-387 — Structured Recommendation Object
**Status: DEFERRED**
Recommendations contain what, why, evidence, expected impact, risk, alternatives, suggested action and confidence.

### ACT-388 — Recommendation Prioritization
**Status: DEFERRED**
Recommendation priority considers impact, urgency, confidence, risk, effort and dependencies rather than arbitrary AI importance.

### ACT-389 — Recommendation Deduplication
**Status: DEFERRED**
Repeated recommendations use fingerprinting, status, previous outcomes and suppression/cooldown to avoid unnecessary repetition.

### ACT-390 — Recommendation Lifecycle
**Status: DEFERRED**
Recommendations follow GENERATED → REVIEWED → ACCEPTED/REJECTED → ACTIONED → EVALUATED with applicable exception states.

### ACT-391 — Rejected Recommendation Memory
**Status: DEFERRED**
Owner rejection context is retained according to memory policy so identical recommendations are not repeatedly presented without justification.

### ACT-392 — New Evidence Reconsideration
**Status: DEFERRED**
A previously rejected recommendation may return when material new evidence exists, with the changed evidence explained.

### ACT-393 — Recommendation Outcome Evaluation
**Status: DEFERRED**
Executed recommendations record action, expected result, actual result, success/failure and lessons for future evaluation.

### ACT-394 — Recommendation vs Owner Decision
**Status: DEFERRED**
AI recommendation and Owner decision are separate records. Owner can accept, reject, modify or defer.

### ACT-395 — Decision Audit Trail
**Status: DEFERRED**
Important decisions record decision maker, timestamp, recommendation/evidence, selected option, modifications and resulting action.

### ACT-396 — Prioritized Daily Business Brief
**Status: DEFERRED**
Daily Brief summarizes important revenue, orders, customers, issues, changes, pending decisions, recommendations and system health without dumping all data.

### ACT-397 — Weekly Business Review
**Status: DEFERRED**
Weekly Review compares current/previous performance, targets, sales, finance, customers, operations, incidents and recommendations.

### ACT-398 — Monthly Strategic Review
**Status: DEFERRED**
Monthly Review focuses on trajectory, recurring patterns, profitability, retention, operational efficiency, strategic opportunities and risks.

### ACT-399 — Configurable Owner Alert Threshold
**Status: DEFERRED**
Owner alerts are triggered according to configurable impact, urgency, risk and business-significance thresholds.

### ACT-400 — Alert Deduplication
**Status: DEFERRED**
Repeated alerts use fingerprinting, cooldown and aggregation, with escalation when severity materially increases.

### ACT-401 — Alert Escalation
**Status: DEFERRED**
Material issues can escalate from LOW → MEDIUM → HIGH → CRITICAL according to configured impact/risk rules.

### ACT-402 — Structured Business Targets
**Status: DEFERRED**
Owner-defined targets such as revenue, orders, conversion, retention and expenses have explicit period and version.

### ACT-403 — Target vs Actual Analysis
**Status: DEFERRED**
The system calculates TARGET → ACTUAL → GAP → TREND, while AI analyzes causes and options separately.

### ACT-404 — Owner-Controlled Target Changes
**Status: DEFERRED**
AI cannot autonomously change business targets. Target changes require Draft → Review → Owner Approval → Active.

### ACT-405 — Scoped Benchmarking
**Status: DEFERRED**
Benchmarking can compare periods, products, channels, segments or business units within authorized scope. Cross-tenant benchmarking requires explicit authorization and safe aggregation.

### ACT-406 — Product Intelligence
**Status: DEFERRED**
AI Analyst can analyze best sellers, slow movers, margins, stock velocity and returns/conversion, while price/stock decisions remain deterministic/authorized.

### ACT-407 — Customer Intelligence
**Status: DEFERRED**
AI can analyze repeat purchase, segments, retention, churn signals, LTV estimates and engagement while clearly distinguishing estimates from actuals.

### ACT-408 — Operational Intelligence
**Status: DEFERRED**
AI Analyst can analyze response time, workflow failures, support volume, integration health, onboarding delays and incident trends.

### ACT-409 — Intelligence Data Freshness
**Status: DEFERRED**
AI Analyst exposes the freshness of data used. Stale data may reduce confidence or block analyses that require current information.

### ACT-410 — Intelligence Guardrail
**Status: DEFERRED**
AI Analyst cannot directly change facts, KPI definitions, targets, transactions, policies or configurations based on analysis. Intelligence follows DATA → ANALYSIS → INSIGHT → RECOMMENDATION → OWNER DECISION → AUTHORIZED ACTION → RESULT → EVALUATION.
---

## DECISION CLASSIFICATION & IMPLEMENTATION STATUS

### Purpose
The ACT numbers are architectural decisions, not 1:1 feature tickets. A decision can be approved while its implementation is intentionally deferred.

### Status meanings
- **ACTIVE** — relevant to the current implementation scope and may be used as an implementation/audit requirement for the active phases. It does not mean every edge case is already implemented.
- **DEFERRED** — approved architecture, but implementation is intentionally postponed. Jules must not implement it merely because it is present in this document.
- **FUTURE** — long-horizon direction/idea. No implementation requirement until a future phase explicitly activates it.
- **MERGED/DUPLICATE** — reserved classification for future consolidation if a decision is later proven redundant. No current ACT is silently deleted.

### Current scope classification
- **ACT-001–009:** ACTIVE
- **ACT-010:** FUTURE
- **ACT-011–041:** ACTIVE
- **ACT-042:** FUTURE
- **ACT-043–290:** ACTIVE
- **ACT-291–330:** DEFERRED
- **ACT-331–370:** DEFERRED
- **ACT-371–410:** DEFERRED

### Important implementation rule
A status of ACTIVE means “architecturally applicable to the current build/audit scope”; it does not mean “the entire decision must already exist as a feature.” Implementation is still governed by the current phase, acceptance criteria, dependency graph and approved implementation plan.

A status of DEFERRED or FUTURE is not a lost decision. Its architectural direction remains recorded, but it is not a current coding requirement.

### Current project boundary
The current implementation baseline remains the already-accepted foundation through **Phase 6.1G**. The next implementation phase must be determined from the actual repository state and an independent audit, not by the mere existence of future ACT decisions.

### Governance rule
Before starting a new implementation phase:
1. Select only ACTs whose status and phase make them applicable.
2. Convert applicable ACTs into explicit implementation requirements.
3. Audit against those requirements.
4. Do not implement DEFERRED/FUTURE architecture opportunistically.
5. If a later feature needs a currently DEFERRED/FUTURE decision, promote it deliberately during phase planning rather than silently treating it as ACTIVE.

### LOCKED STATUS
ACT-001 → ACT-410 remain **APPROVED/LOCKED decisions**, with implementation status classified independently above.

