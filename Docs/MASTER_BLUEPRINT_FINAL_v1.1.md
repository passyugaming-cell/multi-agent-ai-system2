# AI BUSINESS OPERATING SYSTEM

# MASTER BLUEPRINT v1.1

## Canonical Product, Architecture, Business & Development Direction

**Status:** Living document / canonical project context  
**Companion document:** `docs/MASTER_EXECUTION_PLAN.md`  
**Primary market:** Indonesia / UMKM / business clients  
**Primary channel:** WhatsApp-first  
**Architecture:** Universal Core / multi-tenant  
**Primary AI:** Gemini 3.1 Flash-Lite through central AIGateway  
**Backend:** Python + FastAPI + SQLAlchemy async + PostgreSQL  
**Primary coding agent:** Jules  
**Architecture / QA reviewer:** ChatGPT  
**Final authority:** Project Owner  

---

# 0. CARA MENGGUNAKAN DOKUMEN INI

Blueprint ini adalah dokumen canonical untuk memahami:

- visi produk
- tujuan bisnis
- arsitektur
- prinsip AI
- security
- data
- workflow
- agents
- billing
- integrations
- roadmap
- keputusan LOCKED
- Definition of Done
- arah pengembangan jangka panjang

Ketika ada permintaan pengembangan baru:

1. Pahami visi produk.
2. Baca arsitektur yang sudah ada.
3. Cek keputusan LOCKED.
4. Cek phase yang sudah terverifikasi.
5. Audit repository aktual.
6. Tentukan komponen existing yang paling tepat.
7. Reuse sistem yang sudah ada.
8. Cek tenant isolation, security, billing, entitlement, AI authority, event, workflow, audit, analytics.
9. Tentukan phase yang tepat.
10. Baru desain teknis dan implementasi.

Jangan menganggap setiap fitur baru sebagai alasan membuat arsitektur baru.

Feature mapping utama:

- AI baru → `AIGateway + AgentRegistry + Agent`
- Marketing AI → `Agent + Workflow + Analytics`
- Channel baru → `Channel Adapter`
- Payment provider baru → `Payment Provider Adapter`
- CRM/integrasi baru → `Integration Adapter`
- Paket/add-on → `Plan + Addon + Entitlement + Usage`
- Report → `Analytics / BI`
- Tindakan berisiko → `ApprovalSystem`
- Event → `EventBus`
- Proses berulang → `WorkflowEngine`
- Pekerjaan terkoordinasi → `TaskSystem`
- Pengetahuan → `Knowledge System`
- Keputusan bisnis jangka panjang → `Business Memory`
- Engineering reliability → `AI Technician` di atas monitoring, diagnostics, Jules/GitHub workflow; bukan subsystem terpisah yang menggandakan core.

---

# 1. VISI BESAR

Project ini bukan sekadar jasa membuat bot WhatsApp.

Produk yang dibangun adalah:

# AI BUSINESS OPERATING SYSTEM

Sebuah platform SaaS multi-tenant yang membantu bisnis menjalankan operasi dengan AI secara terkontrol.

Kemampuan jangka panjang:

- Customer Service
- Sales
- Support
- Follow-up
- Customer Management
- Knowledge Management
- Business Data
- Order Management
- Automation
- Analytics
- Business Intelligence
- Billing
- Integrations
- AI Management
- Owner AI
- Multi-channel communication
- Business recommendations
- Engineering/reliability assistance

WhatsApp adalah channel utama pada fase awal, bukan batasan arsitektur.

## Filosofi

> **Build once, configure many, activate gradually.**

Satu Universal Core melayani banyak tenant.

Client tidak memperoleh codebase terpisah.

Perbedaan antar-client berasal dari:

- tenant configuration
- business data
- knowledge
- permissions
- plan
- add-ons
- integrations
- workflows
- entitlements
- usage limits
- branding/configuration yang memang diperlukan

---

# 2. MASALAH YANG DISELESAIKAN

Target bisnis/UMKM sering mengalami:

- chat customer terlalu banyak
- pertanyaan berulang
- admin kewalahan
- response lambat
- follow-up terlewat
- data produk tidak konsisten
- stok/harga harus dicek manual
- customer history tersebar
- lead tidak ter-follow-up
- order harus diproses manual
- knowledge bisnis tidak terstruktur
- automation terlalu kaku
- analytics kurang jelas
- AI umum sering hallucinate
- owner sulit mengetahui kondisi bisnis
- banyak tools tidak terhubung

AI Business OS harus menyelesaikan masalah tersebut tanpa mengorbankan kontrol owner.

---

# 3. POSITIONING

Positioning:

> **AI Business Operating System untuk bisnis Indonesia, WhatsApp-first.**

Bukan:

- chatbot keyword sederhana
- AI wrapper
- sekadar auto-reply
- sekadar CRM
- sekadar automation tool

Keunggulan utama:

> **AI bebas memahami percakapan, tetapi tetap terikat pada data bisnis, permission, workflow, dan approval.**

---

# 4. PRINSIP PRODUK

1. Simple for client.
2. Powerful underneath.
3. One core.
4. Multi-tenant.
5. Self-service secara bertahap.
6. AI controlled.
7. Data authoritative.
8. Deterministic-first.
9. Automation observable.
10. Owner remains in control.
11. Security by default.
12. Cost measurable.
13. Upgrade without rebuilding the bot.
14. New channels reuse the same core.
15. New features reuse existing subsystems.
16. Complexity is introduced only when justified.

---

# 5. TARGET CUSTOMER

Primary:

- UMKM Indonesia
- online sellers
- retail
- fashion
- food & beverage
- service businesses
- small agencies
- appointment/booking businesses
- businesses receiving significant WhatsApp inquiries

Later:

- growing SMB
- multi-branch businesses
- agencies/resellers
- enterprise

---

# 6. BUSINESS MODEL

Revenue sources:

```text
Subscription
+
Setup Fee
+
Add-ons
+
Custom Service
+
Enterprise
+
Reseller / White-label (future)
```

Subscription creates recurring MRR.

Setup/custom work can cover onboarding and integration costs.

---

# 7. PLAN — STARTER

Target price:

**Rp299.000 / bulan**

Target:

UMKM yang membutuhkan AI Customer Service dan operasi dasar.

Core capabilities:

- 1 WhatsApp
- AI Customer Service
- FAQ
- Knowledge Base
- Products/services
- Price
- Variants
- Simple stock
- Customer database
- Conversation history
- Basic order
- Cart
- Human handoff
- Admin access
- Bot ON/OFF
- Basic analytics
- Basic automation
- Basic dashboard
- AI usage tracking

Target limits:

- 1 WhatsApp
- 3 admins
- 1.000 active customers/month
- 3.000 AI credits/month
- 2.000 automation runs/month
- 5.000 outbound platform messages
- 5 GB storage

Actual commercial limits must remain configurable through plan/entitlement systems.

Meta/WhatsApp provider fees are treated separately where applicable.

---

# 8. PLAN — PRO

Target price:

**Rp799.000 / bulan**

Starter plus:

- AI Memory
- advanced knowledge
- AI Sales
- AI Support
- AI Follow-up
- lead qualification
- conversation analysis
- workflow builder
- scheduled automation
- abandoned cart
- reminders
- broadcast
- segmentation
- campaigns
- multiple admins
- assignment
- round robin
- internal notes
- advanced analytics
- conversion analytics
- AI resolution analytics
- customer segmentation
- AI recommendations
- API
- webhooks
- Google Sheets
- Make
- n8n
- Zapier connector

Target limits:

- 2 WhatsApp
- 10 admins
- 5.000 active customers
- 15.000 AI credits
- 10.000 automation runs
- 25 GB storage

---

# 9. PLAN — BUSINESS

Target price:

**Rp1.999.000 / bulan**

Pro plus:

- Owner AI
- AI Sales
- AI Client Manager
- AI Support
- AI Analyst
- AI Data Manager
- custom AI Agent
- advanced BI
- forecast
- anomaly detection
- trend detection
- Business Health Score
- Daily Brief
- Weekly Review
- multi-channel
- Instagram
- Facebook Messenger
- Web Chat
- advanced CRM
- advanced API
- custom webhooks
- advanced integrations
- advanced workflow
- custom roles
- granular permissions
- 2FA
- IP restriction
- advanced audit
- advanced reports
- customer 360
- priority support

Exact limits remain entitlement/configuration driven.

---

# 10. PLAN — ENTERPRISE

Target:

Custom.

Indicative positioning:

**Rp5m+ / bulan**, depending on requirements.

Potential capabilities:

- dedicated infrastructure
- stronger isolation
- SSO
- advanced RBAC
- IP restrictions
- advanced audit
- SLA
- custom integrations
- custom retention
- dedicated support
- custom development
- enterprise security controls
- dedicated deployment options

Enterprise MUST continue using Universal Core as much as practical.

---

# 11. ADD-ONS

Add-ons are optional capabilities layered on top of plans.

Examples:

- extra WhatsApp
- AI Technician
- additional AI credits
- additional storage
- advanced analytics
- advanced automation
- premium integrations
- custom AI agent
- priority support
- dedicated infrastructure

Add-ons MUST use:

`Plan + Addon + Entitlement + Usage`

Do not create separate billing architecture for each add-on.

---

# 12. ECONOMICS

Illustrative gross MRR:

```text
10 Starter
= Rp2.990.000/month

30 Starter
= Rp8.970.000/month

100 Starter
= Rp29.900.000/month
```

These are gross revenue examples, not profit projections.

Track:

- revenue/client
- AI cost/client
- infrastructure cost/client
- payment fees
- support cost
- gross margin
- churn
- ARPC
- usage
- add-on revenue
- setup revenue

Never present forecasts as certainty.

---

# 13. LOW-CAPITAL OPERATING STRATEGY

Initial strategy:

- one small VPS
- domain
- PostgreSQL initially on same server if appropriate
- Gemini API
- WhatsApp production path
- HTTPS/SSL
- backups

Delay until justified:

- Kubernetes
- GPU infrastructure
- dedicated database per tenant
- multiple AI providers
- multiple regions
- expensive managed infrastructure
- unnecessary microservices
- complex service mesh

Scale complexity based on actual revenue, load, reliability, and customer requirements.

---

# 14. UNIVERSAL CORE

The Universal Core is the foundation.

Conceptual flow:

```text
Channel
  ↓
Universal Message
  ↓
Identity / Tenant Context
  ↓
Conversation
  ↓
Router
  ↓
Business Logic / Deterministic Engine
  ↓
AI when required
  ↓
Response
  ↓
Channel Adapter
```

Core capabilities include:

- tenant context
- customers
- conversations
- messages
- products
- orders
- billing
- subscriptions
- entitlements
- usage
- knowledge
- memory
- events
- workflows
- tasks
- approvals
- AI Gateway
- agents
- analytics
- integrations
- audit

---

# 15. TENANT MODEL

Tenant is the primary business isolation boundary.

Every tenant-owned object must be scoped correctly.

Examples:

- customers
- products
- orders
- conversations
- messages
- knowledge
- memories
- workflows
- tasks
- integrations
- usage
- subscriptions
- business configuration

Cross-tenant access is a P0 security failure.

---

# 16. TENANT CONTEXT

Tenant context is request-scoped.

Phase 0 uses `X-Tenant-ID` as a temporary tenant-context mechanism.

Important:

> `X-Tenant-ID` is NOT authentication.

Production authorization must derive tenant access from authenticated identity and authorization.

Tenant context must be:

- validated
- request-scoped
- reset after request
- never leaked between concurrent requests

---

# 17. AUTHENTICATION & AUTHORIZATION

Production authorization model:

```text
Authenticated User
 ↓
Trusted Actor Context
 ↓
Authorized Tenant
 ↓
Role / Permission
 ↓
Operation
```

Client-supplied:

- tenant ID
- actor role
- actor permissions
- actor ID

must not become authorization authority by themselves.

Authorization must fail closed.

Missing trusted actor context must not silently grant access.

---

# 18. RBAC / PERMISSIONS

Permission checks should exist at the correct layer.

Examples:

- business data read/write
- knowledge read/write/approve
- customer access
- order management
- billing
- payment
- refund
- integration management
- workflow management
- task management
- analytics
- owner AI
- administration

Permissions must be tenant-scoped.

---

# 19. AI PHILOSOPHY

AI is the reasoning layer.

AI is NOT the system of record.

AI can:

- interpret
- classify
- summarize
- reason
- recommend
- plan
- generate language
- coordinate permitted actions

AI must remain bounded by:

- source of truth
- tools
- permissions
- entitlements
- workflows
- approvals
- usage limits
- safety rules

---

# 20. AI SOURCE OF TRUTH

AI must not be source of truth for:

- price
- stock
- invoice
- payment
- subscription
- entitlement
- customer ID
- order status
- payment status
- system configuration
- permissions

If authoritative information exists in the database or deterministic system, retrieve it.

---

# 21. DETERMINISTIC-FIRST

Preferred decision order:

```text
Request
 ↓
Can DB / deterministic rule answer?
 ├── YES → deterministic result
 └── NO
      ↓
Need reasoning / language?
 └── AI
```

Example:

Customer asks:

> Harga Hoodie berapa?

System should retrieve official price from business data.

AI may format the answer, but should not invent the price.

---

# 22. AI GATEWAY

All AI provider interaction must pass through:

`AIGateway`

Responsibilities:

- provider abstraction
- model selection
- request normalization
- response normalization
- usage tracking
- cost attribution
- timeout
- retry limits
- context limits
- failure handling
- provider independence

No arbitrary module may call an AI SDK directly.

---

# 23. AI PROVIDER STRATEGY

MVP:

**Gemini 3.1 Flash-Lite**

Architecture must remain provider-independent.

Potential future providers may include:

- DeepSeek
- Groq
- OpenAI
- other providers

Do not implement multi-provider routing until justified by:

- business need
- benchmark
- reliability
- cost
- availability

Provider-specific logic must remain behind the AIGateway.

---

# 24. AI USAGE TRACKING

Track:

- tenant_id
- request_id
- agent
- task
- model
- input tokens
- output tokens
- calculated cost/credits
- timestamp
- success
- latency

Raw token data should be retained where appropriate.

Usage attribution must support:

- tenant billing
- cost analysis
- plan limits
- alerts
- AI health monitoring

---

# 25. AI COST SAFETY

Suggested budget thresholds:

```text
70%
→ warning

85%
→ economy mode / warning

100%
→ block or restrict according to plan/policy
```

AI must have:

- rate limit
- timeout
- retry limit
- context limit
- usage tracking
- cost attribution
- failure handling

No AI runaway.

---

# 26. CONTEXT MANAGEMENT

AI should not receive the entire conversation history on every request.

Preferred context:

```text
Recent messages
+
Conversation summary
+
Relevant memory
+
Relevant knowledge
+
Relevant DB data
+
Current task
+
Relevant tool results
```

Only necessary data should be included.

Tenant scope must remain intact.

---

# 27. AI AUTHORITY MODEL

Risk levels:

- LOW
- MEDIUM
- HIGH
- CRITICAL

## LOW

Can execute automatically when authorized.

Examples:

- FAQ answer
- summary
- recommendation
- internal task creation

## MEDIUM

Requires confirmation or policy-based control.

## HIGH

Requires Human Owner approval.

## CRITICAL

Human-only.

Examples:

- critical security policy changes
- critical data deletion
- major production changes
- high-risk financial actions
- selected payment/refund actions

---

# 28. APPROVAL OBJECT

Approval should contain:

- action
- target
- reason
- expected result
- risk
- evidence
- confidence
- requester
- status
- timestamp

Statuses:

```text
PENDING
APPROVED
REJECTED
MODIFIED
EXPIRED
CANCELLED
```

Required safety concepts:

- audit
- kill switch
- least privilege
- emergency override where appropriate

---

# 29. OWNER AI

Owner AI is the business manager/orchestrator.

Flow:

```text
Observe
 ↓
Understand
 ↓
Prioritize
 ↓
Delegate
 ↓
Analyze
 ↓
Recommend
 ↓
Request Approval
 ↓
Act if permitted
 ↓
Verify
 ↓
Learn from result
```

Owner AI is NOT a chatbot with unrestricted database access.

Owner AI uses typed tools and existing subsystems.

---

# 30. OWNER AI CAPABILITIES

Potential capabilities:

- business overview
- daily brief
- weekly review
- client health
- usage analysis
- revenue analysis
- churn risk
- payment issues
- support trends
- automation health
- AI cost analysis
- recommendations
- task coordination
- approval requests
- business memory

---

# 31. OWNER AI RESTRICTIONS

Without appropriate authorization/approval, Owner AI must not:

- change official prices
- issue risky refunds
- perform sensitive payment actions
- delete critical data
- change critical security configuration
- make major production changes
- override permissions
- override tenant boundaries

---

# 32. SPECIALIST AI AGENTS

Initial specialist agents:

1. AI Sales
2. AI Client Manager
3. AI Support
4. AI Data Manager
5. AI Analyst
6. Owner AI

All agents use:

- BaseAgent
- AgentRegistry
- AIGateway
- typed tools
- permissions
- source-of-truth hierarchy

---

# 33. AI SALES

Responsibilities:

- prospect handling
- qualification
- product recommendation
- package recommendation
- proposal
- follow-up
- objection handling
- conversion assistance

Tools may include:

- customer
- product
- pricing
- CRM
- conversation
- proposal
- task
- knowledge

AI Sales cannot change official pricing or discount policy without authorization.

---

# 34. AI CLIENT MANAGER

Responsibilities:

- onboarding
- requirement collection
- validation
- reminders
- configuration assistance
- lifecycle management
- renewal assistance
- churn prevention

Tools:

- client
- onboarding
- configuration
- knowledge
- subscription
- task
- notification

---

# 35. AI SUPPORT

Responsibilities:

- support
- FAQ
- troubleshooting
- complaint classification
- escalation
- handoff
- support summaries

High-risk support actions require approval.

---

# 36. AI DATA MANAGER

Responsibilities:

- business data organization
- import assistance
- validation
- normalization
- data quality detection
- change request preparation

AI Data Manager must not silently overwrite authoritative data.

---

# 37. AI ANALYST

Responsibilities:

- analytics interpretation
- trend explanation
- anomaly investigation
- recommendation
- KPI summaries
- business insights

Analyst distinguishes:

- fact
- inference
- recommendation
- uncertainty

---

# 38. CONFIDENCE MODEL

AI outputs should distinguish:

```text
Finding
Evidence
Confidence
Possible cause
Recommendation
Approval required?
```

Example:

```text
Finding:
AI cost increased 32%.

Evidence:
Usage records.

Confidence:
High.

Possible cause:
Automation volume increased.

Recommendation:
Review workflow X.

Need owner approval:
No.
```

Inference must never be presented as verified fact.

---

# 39. BUSINESS MEMORY

Business Memory stores long-term business context such as:

- owner decisions
- policies
- strategies
- preferences
- constraints
- long-term context

Memory is not transactional truth.

Memory remains tenant-scoped.

---

# 40. CLIENT MEMORY

Client Memory can store useful tenant-scoped customer context.

Examples:

- preferences
- prior conversation summaries
- relevant customer context
- useful non-transactional history

Never allow cross-tenant retrieval.

Memory must not override current authoritative data.

---

# 41. KNOWLEDGE SYSTEM

Knowledge is approved business knowledge used by AI.

Knowledge metadata should include:

- source
- owner
- status
- version
- timestamps
- expiry
- approval
- confidence
- change history
- tenant ownership

---

# 42. KNOWLEDGE LIFECYCLE

```text
DRAFT
 ↓
VALIDATING
 ↓
APPROVED
 ↓
ACTIVE
 ↓
OUTDATED
 ↓
ARCHIVED
```

Creation of content is not the same as approval.

High-impact knowledge changes require appropriate approval.

---

# 43. BUSINESS DATA

Business data includes:

- business profile
- products
- variants
- price
- stock
- customers
- orders
- order items
- policies
- configuration

Authoritative data must remain deterministic.

---

# 44. BUSINESS DATA CHANGE MANAGEMENT

A client statement that changes authoritative data should follow:

```text
Claim
 ↓
Change Request
 ↓
Validation
 ↓
Approval if required
 ↓
Update
 ↓
Audit
```

No silent mutation from AI conversation.

---

# 45. UNIVERSAL MESSAGE

Channels normalize inbound communication into a universal representation.

Conceptually:

```text
WhatsApp
Instagram
Messenger
Web Chat
     ↓
Universal Message
     ↓
Universal Conversation
```

Business logic should not live inside channel-specific handlers.

---

# 46. WHATSAPP-FIRST

WhatsApp is the primary channel for initial commercial launch.

WhatsApp adapter responsibilities:

- receive
- normalize
- send
- provider-specific authentication/verification

Business logic remains in Core.

---

# 47. FUTURE MULTI-CHANNEL

Future channels may include:

- Instagram
- Facebook Messenger
- Web Chat
- other supported channels

They must reuse:

- Universal Customer
- Universal Conversation
- Universal Router
- Universal AI
- Universal Workflow
- Universal Analytics

No duplicated business logic per channel.

---

# 48. CUSTOMER IDENTITY

Customer identity should be reusable across channels where identity can be safely resolved.

Do not assume channel identity automatically equals a global customer identity without validation.

Identity resolution must preserve tenant isolation.

---

# 49. CONVERSATION FLOW

Target flow:

```text
Customer message
 ↓
Channel adapter
 ↓
Universal message
 ↓
Tenant resolution
 ↓
Customer identity
 ↓
Conversation
 ↓
Router
 ↓
Deterministic business logic
 ↓
AI if required
 ↓
Response
 ↓
Channel adapter
 ↓
Customer
```

Every stage should preserve:

- tenant_id
- correlation_id
- causation_id
- request_id where applicable

---

# 50. DETERMINISTIC ROUTER

Router should prefer deterministic intent/operations where possible.

Examples:

- greeting
- product list
- price
- stock
- variant
- product info
- order
- cart
- FAQ
- handoff
- unknown

AI is used when interpretation/reasoning is genuinely required.

---

# 51. HUMAN HANDOFF

Handoff is a first-class capability.

Triggers may include:

- customer requests human
- complaint
- sensitive case
- repeated uncertainty
- high-risk action
- low confidence
- business policy requiring human handling

Handoff should preserve context for the human operator.

---

# 52. HANDOFF CONTEXT

A human should receive useful context:

- customer
- conversation
- reason
- recent messages
- relevant order
- relevant business data
- AI summary
- actions already taken
- pending task
- risk level

No sensitive data should be exposed beyond authorized scope.

---

# 53. ORDER SYSTEM

Orders are deterministic transactions.

AI may assist with:

- intent interpretation
- item selection
- clarification
- summary

Order creation must use deterministic validation for:

- product
- variant
- price
- quantity
- stock
- customer
- tenant

---

# 54. CART

Cart may contain:

- products
- variants
- quantities
- current authoritative pricing
- totals

Final order validation must re-check authoritative data.

Never rely on stale AI-generated totals.

---

# 55. BILLING CORE

Billing is deterministic.

Core concepts:

- Plan
- PlanFeature
- PlanLimit
- Addon
- TenantAddon
- Subscription
- SubscriptionHistory
- Invoice
- InvoiceItem
- Payment
- Usage
- Entitlement

---

# 56. SUBSCRIPTION LIFECYCLE

Conceptually:

```text
REGISTER
 ↓
INVOICE
 ↓
PAYMENT
 ↓
VERIFIED
 ↓
SUBSCRIPTION ACTIVE
 ↓
PROVISIONING
 ↓
ONBOARDING
 ↓
OPERATE
 ↓
RENEW / UPGRADE / DOWNGRADE / CANCEL
```

Payment success must be verified deterministically.

---

# 57. ENTITLEMENT

Entitlement determines whether a tenant may use a capability.

Examples:

- AI agent
- WhatsApp connection
- integration
- workflow
- analytics
- memory
- API
- add-on

Features must not depend on plan-name checks scattered throughout code.

Use centralized entitlement logic.

---

# 58. USAGE

Usage tracking should support:

- AI
- automation
- messages
- storage
- customers
- integrations
- other metered features

Usage limits should be tenant-aware and plan-aware.

---

# 59. PAYMENT PROVIDER

Payment architecture:

```text
Billing Core
     ↓
PaymentProvider interface
     ↓
Provider Adapter
     ↓
Provider API
```

Initial real provider:

**Midtrans**

Provider-specific behavior must remain behind the adapter.

---

# 60. PAYMENT SAFETY

Payment systems require:

- signature verification
- replay protection
- idempotency
- tenant mapping
- normalized status
- Decimal money
- retries
- timeout handling
- audit
- permissions
- secure credentials

AI must not declare a payment successful.

---

# 61. REFUND SAFETY

Refund is a potentially high-risk action.

Depending on policy/risk:

```text
Request
 ↓
Evidence
 ↓
Risk assessment
 ↓
Approval
 ↓
Provider action
 ↓
Verification
 ↓
Audit
```

---

# 62. PROVISIONING

After verified payment:

```text
Verified Payment
 ↓
Subscription ACTIVE
 ↓
TenantProvisioner
 ↓
Default configuration
 ↓
Default workflows
 ↓
Knowledge categories
 ↓
AI guardrails
 ↓
Permissions
 ↓
Readiness check
 ↓
ONBOARDING / CONFIGURING
```

Provisioning must be idempotent.

---

# 63. CLIENT EXPERIENCE

Target journey:

```text
Discover platform
 ↓
Choose plan
 ↓
Register
 ↓
Tenant created
 ↓
Invoice
 ↓
Payment
 ↓
Verified payment
 ↓
Subscription active
 ↓
Provisioning
 ↓
Progressive onboarding
 ↓
Import/configure business data
 ↓
Connect WhatsApp
 ↓
Test AI
 ↓
Activate
 ↓
Customer first message
 ↓
Operate
 ↓
Analytics
 ↓
Upgrade / Add-ons
 ↓
Renewal
```

---

# 64. PROGRESSIVE ONBOARDING

Do not ask the client for every piece of information at registration.

Progressively collect:

1. business identity
2. contact information
3. business category
4. operating hours
5. products/services
6. pricing
7. policies
8. payment methods
9. shipping/fulfillment
10. WhatsApp connection
11. AI behavior preferences
12. optional integrations

Readiness should be measurable.

---

# 65. SELF-SERVICE TARGET

The client should eventually be able to:

- register
- choose plan
- pay
- get provisioned
- enter business data
- import knowledge
- connect WhatsApp
- test AI
- activate
- monitor usage
- upgrade
- add add-ons
- manage billing

without manual developer intervention for normal flows.

---

# 66. BUSINESS DATA IMPORT

Supported future import sources may include:

- spreadsheets
- CSV
- Google Sheets
- documents
- structured forms
- integrations

Import flow:

```text
Upload / Connect
 ↓
Parse
 ↓
Validate
 ↓
Preview
 ↓
Confirm
 ↓
Persist
 ↓
Audit
```

Never silently import destructive changes.

---

# 67. WORKFLOW ENGINE

Workflow:

```text
Trigger
 ↓
Conditions
 ↓
Actions
 ↓
Result
```

Requirements:

- deterministic conditions
- retry
- timeout
- idempotency
- loop protection
- permissions
- execution history
- kill switch
- cost/rate controls

---

# 68. EVENT BUS

Event-driven architecture should use an EventBus for important system events.

Event categories may include:

- client
- payment
- WhatsApp
- AI
- workflow
- system
- subscription
- order
- integration

Events should preserve:

- event_id
- tenant_id
- event_type
- occurred_at
- payload
- source
- correlation_id
- causation_id
- idempotency_key
- schema_version

---

# 69. TASK SYSTEM

Task lifecycle:

```text
CREATED
 ↓
ASSIGNED
 ↓
IN_PROGRESS
 ↓
WAITING_DATA / WAITING_APPROVAL
 ↓
COMPLETED
```

Possible terminal states:

- FAILED
- BLOCKED
- CANCELLED

Tasks can be generated by:

- agents
- workflows
- support
- billing
- owner operations

---

# 70. APPROVAL SYSTEM

Approval is centralized.

Do not create separate approval architectures for every feature.

Approval integrates with:

- Owner AI
- workflows
- agents
- billing
- payments
- sensitive data changes
- production changes

---

# 71. ANALYTICS

Analytics layers:

```text
Data
 ↓
Analysis
 ↓
Intelligence
```

Data:

What happened?

Analysis:

Why?

Intelligence:

What should we do?

AI can help with interpretation, but underlying metrics remain deterministic.

---

# 72. BUSINESS HEALTH SCORE

Business Health Score should combine relevant business/platform indicators.

Output:

- score
- trend
- contributing factors
- confidence
- recommended action

Do not create multiple competing health calculators.

---

# 73. CLIENT HEALTH SCORE

Current conceptual weighting:

- Usage 20%
- Reliability 20%
- Engagement 15%
- Business Result 20%
- Support 10%
- Payment 10%
- Adoption 5%

Ranges:

```text
80–100 = Healthy
60–79  = Needs Attention
40–59  = At Risk
0–39   = Critical
```

Reuse the existing deterministic calculator.

---

# 74. ANOMALY DETECTION

Anomaly detection identifies unusual behavior.

It does not automatically mean failure.

Examples:

- AI cost spike
- message spike
- payment failure spike
- workflow failure spike
- latency increase
- customer engagement decline

AI may investigate causes after deterministic detection.

---

# 75. FORECASTING

Forecasting requires enough historical data.

If insufficient:

```text
INSUFFICIENT_DATA
```

Forecasts must:

- show assumptions
- show uncertainty
- avoid false precision
- never be presented as guaranteed outcomes

---

# 76. RECOMMENDATION LOOP

Recommendation is part of a feedback loop:

```text
Data
 ↓
Insight
 ↓
Recommendation
 ↓
Decision
 ↓
Action
 ↓
Result
 ↓
Data
```

Recommendation performance should eventually be tracked.

---

# 77. OWNER DAILY BRIEF

Potential Daily Brief:

- financial snapshot
- new clients
- churn risk
- payment issues
- major support issues
- AI cost
- platform health
- anomalies
- top opportunities
- recommended actions

Insights should include evidence and confidence.

---

# 78. WEEKLY STRATEGIC REVIEW

Potential Weekly Review:

- revenue trend
- MRR
- client growth
- churn
- conversion
- support quality
- AI cost
- automation health
- top customer issues
- business opportunities
- recommendations
- previous recommendation outcomes

---

# 79. OWNER DASHBOARD

Eventually show:

## Overview

- MRR
- active clients
- new clients
- at-risk clients
- payment issues
- AI cost
- platform health

## Financial

- revenue
- subscription
- setup
- add-ons
- custom services
- outstanding
- failed payments
- refunds

## Clients

- plan
- health
- usage
- revenue
- last activity
- payment state

## AI

- requests
- credits
- cost
- latency
- success
- agent breakdown

## Automation

- runs
- success
- failure
- retries

## Alerts

- connection issues
- payment failure
- workflow failure
- AI incident
- support incident

## Tasks

- follow-up
- payment review
- support
- approvals

---

# 80. INTEGRATION FOUNDATION

Universal Integration Foundation contains:

- Integration
- IntegrationConnection
- IntegrationCredential
- IntegrationExecution
- WebhookConfig
- REST API adapter
- Webhook adapter
- provider-specific adapters
- credential encryption
- execution tracking
- EventBus integration
- audit
- tenant isolation

No second integration architecture.

---

# 81. GOOGLE CALENDAR

Google Calendar is the first calendar integration.

Capabilities include:

- entitlement
- OAuth
- OAuth state security
- token exchange
- token refresh
- 401 refresh/retry
- event CRUD
- free/busy
- timezone handling
- workflow actions
- Owner AI tools
- APIs
- events
- permissions
- tenant isolation
- secure credential storage

---

# 82. GOOGLE SHEETS

Google Sheets is an integration capability.

Potential use cases:

- business data import
- business data export
- reporting
- operational sync
- workflow actions

Use the Universal Integration Foundation.

---

# 83. WHATSAPP CLOUD API

WhatsApp Cloud API is the intended production-grade WhatsApp integration path.

Requirements:

- secure credentials
- webhook verification
- inbound normalization
- outbound sending
- tenant mapping
- connection lifecycle
- rate handling
- retries
- audit
- usage
- entitlement

Do not place business logic directly inside the provider handler.

---

# 84. WHATSAPP CONNECTION LIFECYCLE

Conceptual lifecycle:

```text
NOT_CONNECTED
 ↓
CONNECTING
 ↓
CONNECTED
 ↓
VERIFYING
 ↓
ACTIVE
```

Possible failure states:

```text
FAILED
DISCONNECTED
EXPIRED
SUSPENDED
```

Connection management must be tenant-safe and auditable.

---

# 85. CLIENT ACTIVATION

Activation flow:

```text
REGISTER
 ↓
PAYMENT
 ↓
SUBSCRIPTION ACTIVE
 ↓
PROVISION
 ↓
ONBOARD
 ↓
CONNECT WHATSAPP
 ↓
VERIFY
 ↓
TEST AI
 ↓
ACTIVATE
 ↓
CUSTOMER FIRST MESSAGE
```

Activation gates must be deterministic.

---

# 86. FIRST CONVERSATION

First customer message must flow through the same Universal Core as all later messages.

It should:

- resolve tenant
- resolve customer
- reuse/create conversation
- route
- retrieve authoritative business data
- use AI only when needed
- send response
- record usage
- publish events
- preserve auditability

---

# 87. SECURITY ARCHITECTURE

Security principles:

- least privilege
- tenant isolation
- fail-closed authorization
- secure secrets
- encrypted credentials
- rate limiting
- abuse prevention
- audit
- approvals
- kill switch
- secure error handling
- session security
- 2FA where appropriate
- IP restriction for higher tiers where appropriate

---

# 88. SECRETS

Never hardcode:

- API keys
- tokens
- passwords
- private keys
- provider secrets

Use environment/secret management.

Never expose secrets in:

- logs
- API responses
- AI context
- Git
- test fixtures
- reports

---

# 89. AUDIT LOGGING

Audit important actions:

- authentication/security events
- permission changes
- business data changes
- knowledge approval
- billing
- payment
- refunds
- subscription changes
- entitlement changes
- integration changes
- agent actions
- approval decisions
- workflow actions
- sensitive configuration changes

Audit records should preserve:

- who
- what
- tenant
- when
- reason where applicable
- result
- correlation

---

# 90. OBSERVABILITY

Important operations should use:

- request_id
- correlation_id
- causation_id
- structured logs
- audit logs
- execution history

Errors must be diagnosable without exposing secrets or tenant data.

---

# 91. RELIABILITY

System reliability requires:

- health checks
- dependency checks
- error detection
- retry
- timeout
- idempotency
- monitoring
- backups
- recovery procedures
- incident history
- recovery testing where appropriate

---

# 92. INCIDENT RESPONSE

Conceptual lifecycle:

```text
Detect
 ↓
Contain
 ↓
Diagnose
 ↓
Recover
 ↓
Verify
 ↓
Report
 ↓
Learn
```

Incident severity should determine response urgency.

---

# 93. BACKUP & RECOVERY

Production strategy should include:

- database backups
- configuration backups where safe
- appropriate object storage backups
- retention policy
- restore testing
- recovery documentation

A backup that has never been tested should not be assumed reliable.

---

# 94. API STRATEGY

Primary API style:

`/api/v1/`

Future API domains may include:

- customers
- products
- orders
- conversations
- workflows
- tasks
- approvals
- AI
- knowledge
- billing
- integrations
- analytics

APIs must respect:

- authentication
- authorization
- tenant scope
- validation
- idempotency where required
- auditability

---

# 95. TECH STACK

Current target stack:

Backend:

- Python 3.11+
- FastAPI
- Uvicorn
- SQLAlchemy 2.x async
- asyncpg
- PostgreSQL
- Pydantic v2
- pydantic-settings
- Google GenAI SDK

Testing:

- pytest
- pytest-asyncio
- httpx

Infrastructure:

- Redis-compatible queue/cache
- S3-compatible object storage
- Linux / Ubuntu
- VPS/cloud

Future frontend:

- Next.js
- TypeScript
- Tailwind

No Kubernetes requirement for early production.

---

# 96. DATABASE PRINCIPLE

PostgreSQL is the transactional source of truth.

Tenant-owned entities must have tenant scope.

Base model uses:

- UUID
- timestamps

Migrations use Alembic.

Database changes must be:

- migration-backed
- tested
- tenant-safe
- reversible where practical
- ordered correctly

---

# 97. PROVIDER ADAPTER PRINCIPLE

External providers must be isolated behind adapters.

Examples:

```text
PaymentProvider
CalendarProvider
MessagingProvider
StorageProvider
AIProvider
IntegrationProvider
```

Core business logic should not depend directly on provider-specific APIs.

---

# 98. FAILURE & RETRY

Retries must be:

- bounded
- idempotent where possible
- observable

Default workflow retry principle:

**maximum 3 attempts**, unless a phase explicitly defines another safe policy.

Do not retry non-idempotent financial actions blindly.

---

# 99. API / WEBHOOK SECURITY

Webhook processing should verify:

- authenticity/signature
- timestamp/replay where supported
- tenant mapping
- event type
- idempotency
- payload validation

Never trust a provider success message without verification.

---

# 100. CHANGE MANAGEMENT

Changing a LOCKED decision requires:

1. Explain why.
2. Identify affected systems.
3. Identify migration impact.
4. Identify backward compatibility.
5. Identify business impact.
6. Identify security impact.
7. Identify billing/entitlement impact.
8. Propose architecture change.
9. Update Blueprint.
10. Then implement.

Never silently change architecture.

---

# 101. DEFINITION OF DONE

A phase is PASS only when applicable requirements are satisfied:

- requirement implemented
- existing systems reused
- no duplicate subsystem
- tenant isolation verified
- permissions verified
- security reviewed
- migration successful where applicable
- tests pass
- full regression passes
- pre-commit/lint/check passes where configured
- OpenAPI/API verified where relevant
- no hardcoded secrets
- no arbitrary SQL from AI
- no unsafe shell execution
- no unauthorized filesystem access
- no scope creep
- code review blockers resolved
- known limitations documented
- out-of-scope items documented
- architecture changes documented

Never declare PASS merely because coding finished.

---

# 102. TESTING PHILOSOPHY

Minimum where applicable:

1. migration test
2. unit test
3. integration test
4. tenant isolation test
5. permission test
6. idempotency test
7. failure-path test
8. security test
9. regression test
10. full test suite

For payment/integration:

- signature verification
- replay protection
- duplicate webhook
- timeout
- retry
- provider error
- unauthorized access
- tenant mapping
- credential security

Tests must include both success and failure paths.

---

# 103. NO DUPLICATE SYSTEM RULE

Before creating a new:

- service
- repository
- model
- router
- tracker
- calculator
- event bus
- workflow engine
- approval system
- billing system
- health calculator
- AI gateway
- context system
- memory system

search the repository first.

Extend existing functionality when possible.

---

# 104. NO ARBITRARY AI EXECUTION

AI agents must not receive unrestricted:

- SQL
- shell
- Python
- filesystem
- external APIs

Use typed tools with:

- tenant scope
- permission
- input validation
- output validation
- audit

---

# 105. CLIENT EXPERIENCE

Target:

```text
Discover
 ↓
Choose plan
 ↓
Register
 ↓
Tenant
 ↓
Invoice
 ↓
Payment
 ↓
Verified
 ↓
Subscription active
 ↓
Provisioning
 ↓
Progressive onboarding
 ↓
Business data
 ↓
WhatsApp
 ↓
Test AI
 ↓
Activate
 ↓
Customer first message
 ↓
Operate
 ↓
Analytics
 ↓
Upgrade / Add-ons
 ↓
Renewal
```

---

# 106. UPGRADE / DOWNGRADE

Upgrade:

```text
STARTER
 ↓
PRO
 ↓
Entitlement recalculated
 ↓
New features available
```

No new bot/codebase.

Downgrade must consider:

- current usage
- feature dependencies
- active workflows
- WhatsApp connections
- storage
- admin count
- customer count

Do not immediately destroy data solely because of downgrade.

---

# 107. MULTI-CHANNEL PRINCIPLE

Business logic must remain channel-independent.

Channel adapter:

```text
Receive
 ↓
Normalize
 ↓
Send
```

Possible future:

- WhatsApp
- Instagram
- Messenger
- Web Chat

---

# 108. WHITE-LABEL / RESELLER

Future only.

Potential hierarchy:

```text
Platform Owner
 ↓
Reseller / Agency
 ↓
Client Tenant
 ↓
End Customer
```

Still based on Universal Core.

No separate codebase per reseller/client.

---

# 109. ENTERPRISE

Enterprise capabilities may include:

- dedicated infrastructure
- stronger isolation
- SSO
- advanced RBAC
- IP restrictions
- advanced audit
- SLA
- custom retention
- custom integrations
- dedicated support

Enterprise is not an excuse to fork the core unnecessarily.

---

# 110. AI TECHNICIAN — STRATEGIC FUTURE FEATURE

AI Technician is a strategic future capability, NOT an MVP requirement.

Purpose:

> AI Engineering & Reliability layer for the AI Business OS.

Potential responsibilities:

- monitor runtime errors
- diagnose failures
- identify regressions
- detect integration failures
- inspect logs
- analyze stack traces
- inspect deployment changes
- run tests
- predict reliability issues
- prepare repair plans
- orchestrate Jules
- verify fixes
- monitor post-fix behavior

Conceptual architecture:

```text
AI BUSINESS OS
      ↓
   Owner AI
      ↓
 AI Technician
      ↓
 ┌────┼────────┬─────────┐
Monitor Diagnose Predict Orchestrate
                         ↓
                       Jules
                         ↓
                     GitHub PR
                         ↓
                       Tests
                         ↓
                      Review
                         ↓
                     Approval
                         ↓
                     Deploy
                         ↓
                     Verify
```

AI Technician MUST NOT directly edit production as an unrestricted agent.

---

# 111. AI TECHNICIAN SAFETY

Preferred repair flow:

```text
Detect
 ↓
Diagnose
 ↓
Risk assess
 ↓
Prepare change
 ↓
Jules / coding agent
 ↓
PR
 ↓
Tests
 ↓
Review
 ↓
Approval if required
 ↓
Deploy
 ↓
Verify
```

Risk levels:

LOW:

- documentation
- tests
- low-risk code fixes

MEDIUM:

- normal application fixes
- non-critical integration fixes

HIGH:

- billing
- payment
- security
- tenant isolation
- migrations
- production configuration

HIGH/CRITICAL requires human approval.

---

# 112. AI TECHNICIAN IS NOT A JULES WRAPPER

AI Technician should eventually provide:

- incident reasoning
- dependency analysis
- regression detection
- risk assessment
- repair orchestration
- post-deployment verification
- engineering memory
- reliability trends

Jules is the coding executor.

AI Technician is the engineering lifecycle intelligence/orchestration layer.

---

# 113. AI TECHNICIAN ROADMAP STATUS

Status:

**STRATEGIC FEATURE / FUTURE**

Do NOT implement AI Technician during early MVP unless a roadmap phase explicitly authorizes it.

Do not create its architecture prematurely.

When implemented, it must reuse:

- existing EventBus
- TaskSystem
- ApprovalSystem
- Audit
- Analytics
- AIGateway
- GitHub/Jules integration
- existing monitoring/incident systems

---

# 114. PRODUCT ROADMAP

## V1 — COMMERCIAL MVP

Focus:

- WhatsApp AI
- FAQ
- products
- prices
- stock
- customers
- conversations
- orders
- cart
- human handoff
- basic automation
- dashboard
- Starter
- Pro
- billing
- onboarding
- essential integrations
- usage tracking

Goal:

> Get paying clients.

---

## V1.5 — AUTOMATION & INTELLIGENCE

Focus:

- AI memory
- advanced automation
- follow-up
- segmentation
- advanced analytics
- API
- integrations
- stronger CRM
- better self-service

---

## V2 — OWNER INTELLIGENCE

Focus:

- Owner AI
- advanced BI
- multi-channel
- forecast
- anomaly detection
- deeper business intelligence
- recommendation feedback loops

---

## V3 — ENTERPRISE PLATFORM

Focus:

- enterprise
- white-label
- reseller
- dedicated infrastructure
- advanced security
- SLA
- enterprise integrations

---

## FUTURE STRATEGIC

Potential:

- AI Technician
- AI Business App Store
- deeper ERP/POS/inventory capabilities
- more vertical modules
- engineering intelligence
- broader business operating system capabilities

These must be validated before implementation.

---

# 115. AI BUSINESS APP STORE — FUTURE

Potential future architecture:

```text
App
 ↓
Plan
+
Addon
+
Entitlement
+
Usage
```

Apps may include:

- AI Sales
- AI Support
- Booking
- Finance Assistant
- Marketing AI
- Analyst
- AI Technician
- industry-specific modules

No separate core per app.

---

# 116. FEATURE VALIDATION RULE

Before adding a future feature:

1. Validate customer demand.
2. Identify business value.
3. Identify recurring revenue opportunity.
4. Check existing architecture.
5. Check security.
6. Check tenant isolation.
7. Check AI authority.
8. Check billing/entitlement.
9. Define phase.
10. Define non-goals.
11. Only then implement.

---

# 117. WHAT MUST NOT BE DONE

Do not:

- create separate codebase per client
- duplicate AI usage tracker
- duplicate workflow engine
- duplicate billing logic
- duplicate health calculator
- let AI write arbitrary SQL
- let AI execute arbitrary shell/code
- hardcode secrets
- trust client-provided payment success
- let AI invent price/stock
- mix tenant context
- bypass permissions
- bypass approval
- create second integration architecture
- add microservices without real scaling reason
- add all future features into MVP
- declare PASS without testing
- silently change locked architecture
- use LLM for simple deterministic calculations
- leak provider-specific logic into core billing
- present forecasts as certainty

---

# 118. PROJECT SUCCESS CRITERIA

Project success is NOT the number of features.

Success means:

1. One core serves many tenants.
2. Tenants are isolated.
3. Clients can onboard easily.
4. Clients can connect WhatsApp.
5. Bot answers using correct data.
6. Orders/payments are deterministic.
7. Automation is reliable.
8. Owner can see business condition.
9. AI helps without taking control.
10. System grows without major rewrite.
11. Upgrades do not require new bots.
12. AI/infrastructure costs are measurable.
13. Support can handle incidents.
14. Billing works automatically.
15. Platform can generate MRR.
16. Architecture can evolve toward multi-channel and enterprise.

---

# 119. ARCHITECTURE CONFLICT RULE

When a new feature conflicts with locked architecture:

```text
Does feature really require a change?
        ↓
Can existing system handle it?
        ↓
Can it be an adapter/module?
        ↓
Can configuration/entitlement solve it?
        ↓
If not:
Architecture Change Proposal
```

Do not change architecture merely because a new implementation is easier.

---

# 120. DEVELOPMENT PHILOSOPHY

The development loop is:

```text
Understand
 ↓
Audit
 ↓
Design
 ↓
Implement
 ↓
Test
 ↓
Security Review
 ↓
Regression
 ↓
Audit
 ↓
PASS
```

AI coding agents accelerate implementation.

They do not replace architecture governance.

---

# 121. JULES WORKFLOW

Jules is the primary coding executor.

Jules should:

- read Blueprint
- read Execution Plan
- inspect repository
- inspect current state
- reuse existing systems
- implement according to phase
- test
- run regression
- produce evidence
- create PR
- never merge `main` autonomously

The Execution Plan contains the detailed autonomous execution protocol.

---

# 122. CURRENT VERIFIED IMPLEMENTATION SNAPSHOT

This section is a snapshot, not permanent truth.

As of the current project state known to this Blueprint:

Verified/accepted phases:

```text
Phase 0       PASS
Phase 1       PASS
Phase 1.5     PASS
Phase 2.0     PASS
Phase 3.0     PASS
Phase 4.0     PASS
Phase 1.75    PASS
Phase 5       PASS
Phase 6.0     PASS
Phase 6.1A    PASS
Phase 6.1B    PASS
Phase 6.1C    PASS
Phase 6.1D    PASS
Phase 6.1E    PASS
Phase 6.1F    PASS
Phase 6.1G    MERGED / CURRENT IMPLEMENTATION
```

Important:

The repository is the implementation authority.

Before executing the next phase, Jules MUST re-audit GitHub and current tests rather than trusting this snapshot blindly.

Known recent Phase 6.1G audit concerns included authorization hardening, duplicate routes, repository bypass, and security-test validity. These are historical findings and must be revalidated against the current repository before further action.

---

# 123. CURRENT NEXT-PHASE RULE

Do not hardcode a next phase in this document.

Jules must:

1. inspect current repository
2. inspect merged PRs
3. inspect latest phase reports
4. run relevant tests
5. determine actual incomplete work
6. resolve P0/P1 findings first
7. then continue according to dependency order

If Phase 6.1G or another previous phase still contains a verified P0/P1 issue, dependent work must wait.

---

# 124. MASTER DECISION LOG

## LOCKED D1

Product is AI Business Operating System, not merely WhatsApp Bot.

## LOCKED D2

Universal Core / one codebase / multi-tenant.

## LOCKED D3

Human Owner is final authority.

## LOCKED D4

Owner AI is orchestrator and strategic intelligence, not unrestricted administrator.

## LOCKED D5

AI is not source of truth.

## LOCKED D6

Deterministic-first.

## LOCKED D7

All AI provider interaction through AIGateway.

## LOCKED D8

MVP AI model is Gemini 3.1 Flash-Lite.

## LOCKED D9

MVP does not require multi-provider routing.

## LOCKED D10

Business logic must remain channel-independent.

## LOCKED D11

Payment providers use adapters.

## LOCKED D12

Integrations use Universal Integration Foundation.

## LOCKED D13

Premium features use Plan + Addon + Entitlement + Usage.

## LOCKED D14

Risky actions use ApprovalSystem.

## LOCKED D15

Events use EventBus.

## LOCKED D16

Repeated processes use WorkflowEngine.

## LOCKED D17

Coordinated work uses TaskSystem.

## LOCKED D18

Knowledge is governed through lifecycle and approval.

## LOCKED D19

Long-term business decisions may use Business Memory.

## LOCKED D20

Tenant isolation is a P0 requirement.

## LOCKED D21

Authorization must fail closed.

## LOCKED D22

No hardcoded secrets.

## LOCKED D23

No arbitrary AI SQL/shell/code.

## LOCKED D24

No duplicate subsystem without architectural justification.

## LOCKED D25

No unnecessary microservices in early stages.

## LOCKED D26

No autonomous merge to main.

## LOCKED D27

Final merge requires independent review / PASS.

## LOCKED D28

AI Technician is a future strategic feature, not an MVP requirement.

---

# 125. FINAL MASTER PRINCIPLE

> **Kita tidak sedang membuat kumpulan fitur. Kita sedang membangun satu operating system bisnis yang dapat berkembang.**

Every feature should strengthen the same system.

Not create another system beside it.

```text
Universal Core
→ reusable

AI
→ controlled

Data
→ authoritative

Workflow
→ deterministic

Events
→ observable

Approvals
→ safe

Analytics
→ measurable

Billing
→ deterministic

Security
→ fail-closed

Tenant
→ isolated

Human Owner
→ final authority
```

The system should be:

```text
Human Owner
     ↓
Product / Architecture Authority
     ↓
MASTER BLUEPRINT
     ↓
MASTER EXECUTION PLAN
     ↓
Universal Core
     ↓
AI / Agents / Workflows / Integrations
     ↓
Data / Knowledge / Memory
     ↓
Events / Tasks / Approvals / Analytics
     ↓
Tests / Security / Observability
     ↓
Reliable Business Operations
```

> **Maximum safe automation, minimum unnecessary complexity, and permanent human control over critical decisions.**

---

# UPDATE POLICY

This document is a living document.

Update it when:

- a major architecture decision changes
- a locked decision changes intentionally
- a roadmap phase is verified PASS
- a major feature is added
- a feature is deprecated
- a security architecture changes
- a billing architecture changes
- an important product decision changes

Do not update historical status merely to make the document look cleaner.

Use:

```text
## v1.X — YYYY-MM-DD

### New
- ...

### Changed
- ...

### Locked
- ...

### Deprecated
- ...

### Phase Status
- ...

### Reason
- ...
```

---

# END OF MASTER BLUEPRINT v1.1
