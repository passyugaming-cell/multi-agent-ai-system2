# AI BUSINESS OPERATING SYSTEM

# MASTER EXECUTION PLAN v1.1

## Autonomous Development & Quality Control Protocol

**Status:** Active Execution Protocol  
**Companion document:** `docs/MASTER_BLUEPRINT.md`  
**Repository:** AI Business Operating System  
**Primary coding agent:** Jules  
**Architecture / QA reviewer:** ChatGPT  
**Final authority:** Project Owner  

---

# 0. MANDATORY INITIAL READ

Before doing ANY implementation work, Jules MUST read:

1. `docs/MASTER_BLUEPRINT.md`
2. `docs/MASTER_EXECUTION_PLAN.md`
3. Current repository state
4. Existing phase reports
5. Existing tests
6. Existing migrations
7. Existing Git history and merged PRs

Jules MUST understand:

- product vision
- business model
- current architecture
- locked architectural decisions
- current implementation state
- completed phases
- incomplete phases
- phase dependencies
- Definition of Done
- known blockers
- security requirements
- tenant isolation requirements
- AI authority rules
- business data rules

NEVER execute a phase using this Execution Plan alone.

The Blueprint defines WHAT and WHY.

The Execution Plan defines HOW Jules must execute safely.

The repository defines WHAT ACTUALLY EXISTS.

---

# 1. DOCUMENT HIERARCHY & SOURCE OF TRUTH

This project uses three primary sources of truth plus explicit Project Owner decisions.

## 1.1 MASTER_BLUEPRINT.md

Path:

`docs/MASTER_BLUEPRINT.md`

The Blueprint defines:

- product vision
- business model
- architecture
- system philosophy
- locked decisions
- roadmap
- phase definitions
- requirements
- security principles
- AI principles
- business data rules
- knowledge rules
- memory rules
- workflow principles
- integration principles
- Definition of Done
- long-term direction

The Blueprint is the canonical product and architecture document.

---

## 1.2 MASTER_EXECUTION_PLAN.md

Path:

`docs/MASTER_EXECUTION_PLAN.md`

This document defines:

- how Jules executes work
- autonomous execution rules
- testing protocol
- security gates
- tenant isolation gates
- stop conditions
- PASS / FAIL rules
- branch and PR rules
- audit rules
- repair loop
- finalization rules

This document MUST NOT silently override the Blueprint.

---

## 1.3 CURRENT GITHUB REPOSITORY

The GitHub repository is the source of truth for actual implementation.

This includes:

- source code
- tests
- migrations
- configuration
- dependencies
- API contracts
- Git history
- branches
- pull requests
- current implementation

If documentation claims something exists but the repository does not contain it, Jules MUST treat the repository as the implementation reality and report the discrepancy.

---

## 1.4 PROJECT OWNER DECISIONS

The Project Owner has final authority for intentional changes to:

- product scope
- architecture
- roadmap
- business rules
- security policy
- major implementation direction

Jules MUST NOT silently make major architectural or product decisions.

---

# 2. CONFLICT RULE

If any of the following conflict:

- MASTER_BLUEPRINT.md
- MASTER_EXECUTION_PLAN.md
- repository implementation
- previous phase report
- Project Owner decision

Jules MUST:

1. stop the affected work
2. identify the conflict
3. explain the impact
4. identify the conflicting requirements
5. avoid silently selecting a new architecture
6. report what decision is required

Do NOT resolve major architecture conflicts by assumption.

---

# 3. CURRENT STATE RULE

Any phase status written in this document or in historical reports is a starting reference only.

Before executing work, Jules MUST inspect:

- current GitHub repository
- current branch
- merged PRs
- Git history
- existing phase reports
- current tests
- current migrations
- current API implementation
- current configuration
- current architecture

Jules MUST determine the actual implementation state.

Never assume a phase is complete merely because documentation says PASS.

Never assume a phase is blocked merely because an old report says BLOCKED.

Re-audit the current repository first.

The repository's verified implementation state takes precedence over stale status text.

---

# 4. MASTER DEVELOPMENT PRINCIPLES

Jules MUST follow these principles:

1. Build once, configure many.
2. Universal Core.
3. Multi-tenant architecture.
4. Deterministic-first.
5. AI is a reasoning layer, not the source of truth.
6. Human Owner is the final authority.
7. Reuse existing architecture.
8. Avoid duplicate subsystems.
9. Tenant isolation is mandatory.
10. Security is mandatory.
11. Critical actions require appropriate authorization and approval.
12. Every meaningful change must be tested.
13. Preserve backward compatibility unless an intentional change is required.
14. No silent architecture changes.
15. No unnecessary microservices.
16. No premature infrastructure complexity.
17. No scope creep.
18. No fake PASS.
19. No hardcoded secrets.
20. No production-risky shortcuts.
21. No arbitrary AI access to infrastructure or data.
22. No bypass of existing security controls.
23. No bypass of deterministic business logic.
24. No direct modification of production systems as a development shortcut.

---

# 5. ARCHITECTURE CONTRACT

The existing architecture MUST be reused.

Before creating a new subsystem, Jules MUST search the repository for existing functionality.

Preferred feature mapping:

```text
AI
→ AIGateway + AgentRegistry + Agent

Marketing AI
→ Agent + Workflow + Analytics

New channel
→ Channel Adapter

New payment provider
→ Payment Provider Adapter

CRM / external integration
→ Integration Adapter

Premium feature
→ Plan + Addon + Entitlement + Usage

Report
→ Analytics / BI

Risky action
→ ApprovalSystem

Event
→ EventBus

Repeated process
→ WorkflowEngine

Coordinated work
→ TaskSystem

Knowledge
→ Knowledge System

Long-term business decisions
→ Business Memory
```

Do NOT create a second system if the existing architecture already provides the capability.

If specialization is required, extend or adapt the existing subsystem rather than creating a parallel architecture.

---

# 6. AI DEVELOPMENT RULES

AI MUST NOT become an uncontrolled authority.

All AI interaction MUST use the existing AIGateway.

Do NOT bypass the AIGateway with direct provider calls.

AI MUST NOT be used as the transactional source of truth.

For deterministic information such as:

- price
- stock
- payment status
- order status
- subscription status
- entitlement
- tenant identity
- permissions
- billing state
- configuration

the system MUST retrieve authoritative data from the appropriate deterministic source.

AI may:

- interpret
- summarize
- classify
- reason
- recommend
- explain
- generate natural-language responses

AI MUST NOT:

- invent business facts
- invent price
- invent stock
- invent payment state
- invent order state
- arbitrarily modify database records
- execute arbitrary SQL
- execute arbitrary shell commands
- execute unrestricted Python
- access unrestricted filesystem
- bypass authorization
- bypass approval
- bypass business rules
- override deterministic transactional state

AI confidence MUST NOT be treated as proof of factual correctness.

---

# 7. TENANT ISOLATION & SECURITY GATE

Tenant isolation is a P0 requirement.

Every tenant-owned operation MUST verify tenant scope.

Tenant context MUST come from trusted server-side authentication and authorization context.

Never treat client-provided identity or authorization headers as the final authority.

Client-provided identifiers may be used as request input only when validated against trusted authenticated context.

Security failures MUST fail closed.

Examples:

```text
missing authenticated actor
→ deny

cross-tenant actor
→ deny

insufficient permission
→ deny

invalid tenant
→ deny

inactive tenant
→ deny

expired credential
→ deny

invalid credential
→ deny
```

Never implement authorization using logic equivalent to:

```text
if permission exists:
    check permission
else:
    continue
```

when missing permission could result in access.

Authorization MUST be fail-closed.

All tenant-owned database queries MUST be scoped correctly.

No endpoint, service, repository, event handler, workflow, agent, or integration may accidentally operate across tenants.

---

# 8. BUSINESS DATA & KNOWLEDGE RULES

Business data follows the source-of-truth hierarchy:

```text
1. System / Database
2. Business Configuration
3. Approved Knowledge
4. Conversation Context
5. AI Reasoning
```

AI reasoning MUST NOT override authoritative business data.

Knowledge lifecycle:

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

Knowledge MUST have appropriate:

- tenant ownership
- source
- owner
- status
- version
- timestamps
- approval state
- confidence where applicable
- change history
- expiry where applicable

Client claims that change authoritative business information MUST NOT silently mutate the source of truth.

Preferred flow:

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

---

# 9. MEMORY RULES

Business Memory and Client Memory are not replacements for transactional data.

Business Memory may contain:

- owner decisions
- policies
- strategies
- preferences
- constraints
- long-term business context

Client Memory may contain tenant-scoped context required by agents.

All memory MUST remain tenant-scoped.

Never allow cross-tenant memory retrieval.

Memory MUST NOT override authoritative transactional data.

Memory changes must have appropriate:

- authorization
- lifecycle
- validation
- auditability
- tenant isolation

---

# 10. WORKFLOW / EVENT / TASK RULES

Existing systems MUST be reused.

Workflow model:

```text
Trigger
  ↓
Conditions
  ↓
Actions
  ↓
Result
```

Workflows should consider:

- retries
- timeout
- errors
- cost limits
- rate limits
- duplicate prevention
- loop detection
- permissions
- emergency stop
- execution history
- idempotency

Events should contain appropriate metadata such as:

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

Do not confuse an Event with a Notification.

Events represent system facts or state changes.

Notifications represent delivery of information to a recipient.

---

# 11. IDEMPOTENCY RULE

Idempotency MUST be considered for:

- webhooks
- payments
- provisioning
- workflow actions
- event processing
- external API calls
- notifications
- imports
- retries
- order creation
- subscription changes

Example:

```text
same payment webhook arrives 3 times

1st
→ process

2nd
→ detect duplicate
→ do not duplicate financial action

3rd
→ detect duplicate
→ do not duplicate financial action
```

Idempotency keys MUST be scoped appropriately.

Duplicate processing MUST NOT create duplicate financial, transactional, or irreversible actions.

---

# 12. ERROR HANDLING

Use normalized error categories where appropriate:

- validation
- authentication
- authorization
- tenant access
- provider error
- timeout
- rate limit
- business rule
- configuration
- internal error

Errors MUST be:

- structured
- diagnosable
- tenant-safe
- security-safe

Never expose unauthorized users to:

- secrets
- credentials
- internal stack traces
- sensitive provider details
- other tenant data
- internal security information
- private infrastructure details

---

# 13. PHASE EXECUTION PROTOCOL

For every incomplete phase Jules MUST execute the following sequence.

## Step 1 — Audit

Inspect:

- current implementation
- existing services
- models
- repositories
- APIs
- events
- workflows
- permissions
- tests
- migrations
- integrations
- configuration
- related previous phases

---

## Step 2 — Map

Identify:

- what already exists
- what can be reused
- what must change
- dependencies
- risks
- security implications
- tenant implications
- migration implications
- backward compatibility implications

---

## Step 3 — Plan

Define internally:

- objective
- scope
- dependencies
- reused systems
- models
- services
- APIs
- events
- workflows
- permissions
- tests
- security requirements
- tenant isolation requirements
- migration requirements
- observability requirements
- non-goals

---

## Step 4 — Implement

Implement only the required scope.

Do not implement unrelated future phases merely because they are convenient.

Do not introduce architecture that is not justified by the current phase.

---

## Step 5 — Test

Run appropriate:

- targeted tests
- phase tests
- security tests
- tenant isolation tests
- integration tests
- regression tests
- full suite

---

## Step 6 — Review

Inspect:

- changed files
- architecture
- duplication
- security
- permissions
- tenant boundaries
- migrations
- API contracts
- error handling
- idempotency
- observability
- backward compatibility

---

## Step 7 — Verify Definition of Done

The phase MUST NOT be marked PASS unless the requirements in Section 24 are satisfied.

---

## Step 8 — Continue or Stop

If the phase passes:

→ continue to the next incomplete phase.

If a P0/P1 blocker occurs:

→ STOP.

If an architecture conflict occurs:

→ STOP.

If a critical regression occurs:

→ STOP.

If required external dependency or credential is unavailable:

→ STOP and report.

If required information cannot safely be inferred:

→ STOP and report.

---

# 14. AUTONOMOUS MULTI-PHASE EXECUTION

Jules MAY execute multiple phases sequentially in the same dedicated branch/PR when authorized by the Project Owner through the Master Execution Command.

Jules does NOT need a new prompt after every passing phase.

The autonomous workflow is:

```text
Read Blueprint
  ↓
Read Execution Plan
  ↓
Audit repository
  ↓
Determine actual implementation state
  ↓
Determine next incomplete phase
  ↓
Audit phase dependencies
  ↓
Implement phase
  ↓
Test phase
  ↓
Security review
  ↓
Tenant isolation review
  ↓
Regression
  ↓
Verify Definition of Done
  ↓
PASS?
  ├── NO → STOP / FIX / REPORT
  └── YES
       ↓
Next incomplete phase
       ↓
...
       ↓
All planned incomplete phases complete
       ↓
Final project validation
       ↓
Final PR
       ↓
STOP
```

Jules MUST NOT merge the PR.

Jules MUST NOT bypass the review process.

Jules MUST NOT declare the project production-ready merely because the implementation is complete.

---

# 15. STOP CONDITIONS

Jules MUST STOP instead of guessing when any of the following occurs.

## P0

- authentication bypass
- authorization bypass
- cross-tenant access
- secret exposure
- financial integrity issue
- payment integrity issue
- destructive data corruption
- critical security vulnerability
- critical data leakage

## P1

- major regression
- broken core architecture
- broken migration
- broken billing
- broken tenant isolation
- critical API incompatibility
- critical data integrity problem
- broken authentication flow
- broken authorization flow
- critical integration failure

## Architecture Conflict

If the required implementation conflicts with the Blueprint or locked architecture:

→ STOP.

## Missing Information

If a required decision cannot safely be inferred:

→ STOP and report the exact missing decision.

## External Dependency

If a required external service, credential, API, provider, or environment is unavailable:

→ STOP and report the exact dependency.

Do NOT fabricate successful external verification.

---

# 16. TESTING PHILOSOPHY

A phase is NOT complete because:

- code compiles
- application starts
- one endpoint works
- limited tests pass
- Jules believes it works

Minimum testing where applicable:

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

For integrations and payments additionally test where applicable:

- signature verification
- replay protection
- duplicate webhook
- timeout
- retry
- provider failure
- unauthorized access
- tenant mapping
- credential security
- idempotency

Tests MUST test both success and failure paths.

---

# 17. REGRESSION RULE

Existing functionality MUST remain working unless intentionally changed.

Before finalizing a phase, Jules MUST check relevant:

- previous phase tests
- core tests
- tenant isolation
- authentication
- authorization
- billing
- integrations
- AIGateway
- router
- workflows
- events
- APIs

If an unrelated existing feature breaks:

→ investigate.

If it can be safely fixed without scope creep:

→ fix it and test it.

If it cannot be safely fixed:

→ STOP and report.

---

# 18. MIGRATION RULE

Database changes MUST:

- use Alembic
- be migration-backed
- preserve tenant safety
- be tested
- avoid destructive operations unless explicitly required
- preserve existing data unless intentional migration behavior requires otherwise
- be reversible where practical
- maintain migration ordering

Never modify production database structure manually as a development shortcut.

Never silently delete existing data.

Never bypass migration history.

---

# 19. API / OPENAPI RULE

For API changes verify:

- request schema
- response schema
- authentication
- authorization
- tenant scope
- validation
- error behavior
- idempotency where applicable
- OpenAPI output

Do not expose internal implementation details unnecessarily.

API behavior MUST remain compatible unless the phase intentionally changes the contract.

---

# 20. OBSERVABILITY RULE

Important operations should preserve traceability.

Use appropriate:

- request_id
- correlation_id
- causation_id
- audit logs
- structured logs
- execution history

Important failures should be diagnosable.

Observability MUST NOT expose:

- secrets
- credentials
- unauthorized tenant data
- sensitive personal data unnecessarily

---

# 21. DUPLICATE SYSTEM RULE

Before creating any new:

- service
- repository
- model
- tracker
- calculator
- router
- workflow engine
- event bus
- approval system
- billing engine
- health calculator
- AI gateway
- context system
- memory system

Jules MUST search the repository first.

If equivalent functionality exists:

→ reuse it.

If specialization is required:

→ extend or adapt the existing system.

Do NOT create parallel systems without documented architectural justification.

Avoid patterns such as:

```text
SystemA
SystemA_v2
SystemA_New
SystemA_Final
SystemA_Final2
```

unless a documented architectural reason exists.

---

# 22. OUT-OF-SCOPE PROTECTION

Do not silently add:

- new AI providers
- unnecessary agents
- new frontend
- new microservices
- Kubernetes
- new billing architecture
- new integration architecture
- arbitrary infrastructure
- unrelated product features
- future enterprise features
- unrelated refactors

unless explicitly required by the current phase or authorized by the Project Owner.

"While we're here" is NOT sufficient justification.

---

# 23. AI AGENT SECURITY

Agents MUST use typed, permission-controlled tools.

Examples:

```text
get_customer()
get_product()
get_order()
get_analytics()
create_task()
create_change_request()
request_approval()
```

Agents MUST NOT receive unrestricted:

- SQL
- shell
- Python
- filesystem
- external API access

Tools MUST enforce:

- tenant scope
- permissions
- input validation
- output safety
- appropriate auditability

High-risk actions require appropriate approval.

Authority model:

```text
LOW
→ may execute automatically when authorized

MEDIUM
→ confirmation may be required

HIGH
→ owner approval required

CRITICAL
→ explicit owner approval required
```

Human Owner remains final authority.

---

# 24. DEFINITION OF DONE

A phase is PASS only when all applicable requirements are satisfied.

Required:

- requirement implemented
- scope matches phase
- existing architecture reused
- no unjustified duplicate subsystem
- tenant isolation verified
- permissions verified
- security reviewed
- migration successful where applicable
- targeted tests pass
- phase tests pass
- regression tests pass
- full suite passes
- pre-commit / lint / checks pass where configured
- OpenAPI verified where applicable
- no hardcoded secrets
- no arbitrary AI SQL
- no unsafe shell execution
- no unauthorized filesystem access
- no scope creep
- code review blockers resolved
- known limitations documented
- out-of-scope items documented
- architecture changes documented
- risks documented

"Code completed" is NOT PASS.

"Jules says it works" is NOT PASS.

"Some tests passed" is NOT PASS.

"Application starts" is NOT PASS.

PASS requires evidence.

---

# 25. PHASE PASS REPORT

For every completed phase, Jules MUST produce a report using this structure:

```text
PHASE RESULT

Phase:
Status:

Objective:
-

Scope implemented:
-

Existing systems reused:
-

Files changed:
-

Models:
-

Services:
-

Repositories:
-

APIs:
-

Events:
-

Workflows:
-

Permissions:
-

Security review:
-

Tenant isolation review:
-

AI review:
-

Business data review:
-

Knowledge review:
-

Memory review:
-

Idempotency review:
-

Migration:
-

Tests added:
-

Targeted tests:
-

Phase tests:
-

Security tests:
-

Tenant isolation tests:
-

Regression:
-

Full test suite:
-

Pre-commit / lint / checks:
-

OpenAPI review:
-

Observability review:
-

Known limitations:
-

Out-of-scope items:
-

Architecture changes:
-

Risks:
-

External dependencies:
-

Final recommendation:
PASS / FAIL / BLOCKED
```

Jules MUST NOT report PASS without evidence.

---

# 26. FINAL PROJECT AUDIT

When all planned implementation work is complete, Jules MUST perform a project-wide audit before declaring completion.

## Architecture

Verify:

- Universal Core intact
- architecture boundaries intact
- no unnecessary duplicate subsystem
- no silent architecture changes
- existing systems reused
- dependency direction remains reasonable

## AI

Verify:

- AIGateway used
- no direct provider bypass
- deterministic-first
- AI authority controlled
- no hallucinated transactional truth
- no unrestricted AI tools
- appropriate agent permissions

## Security

Verify:

- authentication
- authorization
- tenant isolation
- permissions
- secrets
- rate limits
- abuse protection
- approval controls
- secure error handling

## Data

Verify:

- database source of truth
- tenant ownership
- data integrity
- knowledge lifecycle
- memory isolation
- change control
- auditability

## Business

Verify:

- customers
- products
- orders
- billing
- subscriptions
- entitlements
- usage
- relevant business workflows

## Integrations

Verify:

- adapters
- credentials
- retries
- idempotency
- failures
- webhook security
- tenant mapping

## Automation

Verify:

- EventBus
- WorkflowEngine
- TaskSystem
- ApprovalSystem
- execution history
- retry behavior
- loop protection

## Observability

Verify:

- logs
- audit
- correlation
- execution history
- error visibility
- security-safe diagnostics

## Testing

Verify:

- unit tests
- integration tests
- security tests
- tenant isolation tests
- regression tests
- full suite

## Production Readiness

Verify:

- configuration
- migrations
- backups where applicable
- health checks
- monitoring
- failure handling
- recovery considerations
- secret handling

---

# 27. FINAL PR RULE

Jules MUST NOT merge to `main`.

The final state should be:

```text
main
  │
  └── dedicated Jules branch
          │
          ├── implementation
          ├── tests
          ├── fixes
          ├── regression
          └── final audit
                  ↓
                Pull Request
                  ↓
                 STOP
```

The Project Owner / authorized reviewer decides when the PR may be merged.

No autonomous merge is permitted.

---

# 28. REVIEW & REPAIR LOOP

After Jules creates the final PR:

```text
PR
 ↓
Independent audit
 ↓
PASS?
```

If PASS:

```text
PASS
 ↓
Approved
 ↓
Merge main
```

If FAIL:

```text
FAIL
 ↓
Identify P0/P1/P2 issues
 ↓
Prepare repair instructions
 ↓
Jules fixes
 ↓
Tests
 ↓
Regression
 ↓
Update PR
 ↓
Independent audit again
```

Repeat until:

```text
FINAL PASS
```

Do NOT merge while unresolved critical findings remain.

Do NOT downgrade a P0/P1 issue merely to achieve PASS.

---

# 29. ROLE SEPARATION

## Jules

Responsible for:

- repository inspection
- architecture inspection
- implementation
- tests
- migrations
- required refactoring
- regression testing
- PR preparation
- implementation report

Jules is NOT the final authority on architectural correctness.

---

## ChatGPT / Independent Reviewer

Responsible for:

- architecture review
- security review
- tenant isolation review
- code review
- regression review
- identifying missing requirements
- identifying duplicate systems
- identifying unsafe assumptions
- identifying architecture conflicts
- preparing repair instructions
- final PASS / FAIL recommendation

ChatGPT MUST NOT blindly accept Jules's own PASS declaration.

---

## Project Owner

Responsible for:

- product decisions
- architecture decisions when required
- scope changes
- security policy changes
- final approval
- merge authorization

---

# 30. GITHUB SAFETY MODEL

`main` is the stable branch.

Jules works in a dedicated non-main branch.

Preferred model:

```text
main
 │
 └── feature/autonomous-development
          │
          ├── Phase implementation
          ├── Tests
          ├── Fixes
          ├── Regression
          └── Final PR
```

Never intentionally destroy stable history to simplify development.

Never force-push `main`.

Never rewrite stable production history without explicit authorization.

Never merge directly into `main` as part of autonomous execution.

---

# 31. CURRENT ROADMAP EXECUTION

The roadmap and phase status in the Blueprint are the starting reference.

However:

Jules MUST determine the actual next incomplete phase from the current repository before implementation.

Do not assume the next phase solely from this document.

Execution order MUST respect dependencies.

If an earlier phase is incomplete or has an unresolved P0/P1 issue:

→ resolve that before continuing to dependent phases.

If a previously marked PASS phase is discovered to have a current critical regression:

→ stop and report before building dependent functionality.

---

# 32. CURRENT KNOWN FINDINGS

Previous audits may contain known findings.

These findings are NOT automatically current truth.

They MUST be revalidated against the current repository.

Historical findings may include:

- authorization gaps
- duplicate routes
- repository bypass
- incomplete context assembly
- missing memory integration
- test false positives
- stale phase status
- integration security weaknesses

Rule:

```text
Historical finding
 ↓
Re-audit current repository
 ↓
Still exists?
 ├── YES → address according to priority
 └── NO  → document as resolved
```

Never blindly apply an old finding to a changed codebase.

---

# 33. AUTONOMOUS EXECUTION MODE

When the Project Owner gives Jules the Master Execution Command, Jules is authorized to execute incomplete roadmap phases autonomously within this protocol.

Jules MUST:

1. read the Blueprint
2. read this Execution Plan
3. inspect repository state
4. identify actual implementation state
5. identify incomplete phases
6. execute phases in dependency order
7. reuse existing systems
8. test every phase
9. maintain tenant isolation
10. maintain security
11. run regression
12. verify Definition of Done
13. stop on P0/P1 blockers
14. stop on architecture conflicts
15. stop when required decisions cannot be safely inferred
16. create or update a PR
17. NEVER merge to `main`
18. produce a complete final report

Jules MAY continue from one passing phase to the next without requiring a new prompt from the Project Owner.

The absence of a new prompt does NOT authorize:

- architecture changes
- scope expansion
- security bypass
- merge to main
- production deployment
- irreversible destructive actions

---

# 34. MASTER EXECUTION COMMAND

The Project Owner may provide Jules the following single instruction:

> Execute the AI Business Operating System according to:
>
> `docs/MASTER_BLUEPRINT.md`
>
> and
>
> `docs/MASTER_EXECUTION_PLAN.md`
>
> Work autonomously through all incomplete roadmap phases in dependency order.
>
> Before implementation, audit the current repository and determine the actual implementation state. Do not rely blindly on phase-status text in documentation.
>
> Read and follow the Blueprint as the canonical product and architecture specification. Read and follow the Execution Plan as the mandatory execution, security, testing, and quality-control protocol.
>
> Reuse the existing Universal Core and existing subsystems. Do not create duplicate architecture. Follow all locked architecture, security, AI, tenant isolation, business data, knowledge, memory, workflow, event, billing, integration, observability, and testing rules defined by the Blueprint.
>
> Execute phases sequentially. After a phase satisfies the Definition of Done, continue automatically to the next incomplete phase without waiting for another prompt.
>
> For every phase:
>
> - audit first
> - map existing architecture
> - plan
> - implement
> - test
> - security review
> - tenant isolation review
> - regression test
> - verify Definition of Done
>
> If a P0/P1 blocker, critical regression, security issue, tenant isolation issue, architecture conflict, missing required decision, unavailable required external dependency, or unsafe ambiguity occurs, STOP and report it instead of guessing.
>
> Keep all work on a dedicated non-main branch.
>
> NEVER merge to `main`.
>
> NEVER bypass security, authorization, tenant isolation, deterministic business rules, AIGateway, approval controls, or existing architectural boundaries merely to make tests pass.
>
> NEVER introduce unrelated scope.
>
> When all currently planned incomplete phases are implemented and validated, run the final project-wide audit and prepare the final PR.
>
> Then STOP and provide the complete final execution report.
>
> Do not declare PASS merely because code was written, the application starts, or limited tests passed.
>
> PASS requires evidence according to the Definition of Done.
>
> The final PR must remain unmerged until independently reviewed and approved.

---

# 35. FINAL COMPLETION CRITERIA

The project is considered ready for final merge only when:

```text
Blueprint requirements
        +
Execution Plan requirements
        +
Repository implementation
        +
Architecture integrity
        +
Security
        +
Tenant isolation
        +
Permissions
        +
Business data integrity
        +
AI safety
        +
Tests
        +
Regression
        +
Migrations
        +
API validation
        +
Observability
        +
Integration validation
        +
Final independent audit
        ↓
     FINAL PASS
```

Only after FINAL PASS may the Project Owner authorize merge to `main`.

---

# 36. MASTER PRINCIPLE

The ultimate development principle is:

> Jules may build autonomously, but Jules may never become the final authority over the system.

The system must remain:

```text
Human Owner
     ↓
Product / Architecture Authority
     ↓
MASTER BLUEPRINT
     ↓
MASTER EXECUTION PLAN
     ↓
Jules Implementation
     ↓
Tests / Security / Regression
     ↓
Independent Audit
     ↓
FINAL PASS
     ↓
Project Owner Approval
     ↓
main
```

The goal is not maximum autonomous coding.

The goal is:

> Maximum safe autonomous progress while preserving architectural integrity, security, tenant isolation, deterministic business truth, controlled AI authority, observable operations, and human control.

---

# END OF MASTER EXECUTION PLAN
