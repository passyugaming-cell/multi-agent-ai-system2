
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
7. Existing Git history / merged PRs

Jules MUST understand:

- product vision
- current architecture
- locked decisions
- current implementation state
- completed phases
- incomplete phases
- dependencies
- Definition of Done
- known blockers
- security requirements
- tenant isolation requirements

NEVER execute a phase using this Execution Plan alone.

The Blueprint defines WHAT and WHY.

The Execution Plan defines HOW Jules must execute safely.

The repository defines WHAT ACTUALLY EXISTS.

---

# 1. DOCUMENT HIERARCHY & SOURCE OF TRUTH

This project uses three primary sources of truth plus explicit project-owner decisions.

## 1.1 MASTER_BLUEPRINT.md

`docs/MASTER_BLUEPRINT.md`

Defines:

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
- Definition of Done
- long-term direction

The Blueprint is the canonical product and architecture document.

---

## 1.2 MASTER_EXECUTION_PLAN.md

`docs/MASTER_EXECUTION_PLAN.md`

Defines:

- how Jules executes work
- execution protocol
- testing protocol
- security gates
- autonomous development rules
- stop conditions
- PASS / FAIL rules
- branch / PR rules
- audit loop
- finalization rules

This document MUST NOT silently override the Blueprint.

---

## 1.3 Current GitHub Repository

The repository is the source of truth for actual implementation.

This includes:

- source code
- tests
- migrations
- configuration
- API contracts
- dependencies
- Git history
- branches
- pull requests

If a document claims something exists but the repository does not contain it, Jules MUST treat the repository as the implementation reality and report the discrepancy.

---

## 1.4 Project Owner Decisions

The Project Owner has final authority for intentional changes to:

- scope
- architecture
- roadmap
- product direction
- security policy
- business rules

Jules MUST NOT silently make major architectural or product decisions.

---

# 2. CONFLICT RULE

If any of the following conflict:

- Blueprint
- Execution Plan
- repository implementation
- previous phase report
- project-owner decision

Jules MUST:

1. stop the affected work
2. identify the conflict
3. explain the impact
4. avoid silently choosing a new architecture
5. report what decision is required

Do NOT resolve major architecture conflicts by assumption.

---

# 3. CURRENT STATE RULE

Any phase status written in this document is a starting snapshot only.

Before executing:

- inspect the current GitHub repository
- inspect merged PRs
- inspect Git history
- inspect existing phase reports
- inspect tests
- inspect migrations
- determine the actual current state

Never assume a phase is complete merely because this document says PASS.

Never assume a phase is blocked merely because an old report says BLOCKED.

Re-audit the current repository first.

---

# 4. MASTER DEVELOPMENT PRINCIPLES

Jules MUST follow these principles:

1. Build once, configure many.
2. Universal Core.
3. Multi-tenant architecture.
4. Deterministic-first.
5. AI is reasoning, not source of truth.
6. Human Owner is final authority.
7. Reuse existing architecture.
8. Avoid duplicate subsystems.
9. Tenant isolation is mandatory.
10. Security is mandatory.
11. Critical actions require appropriate authorization.
12. Every meaningful change must be tested.
13. Every phase must preserve backward compatibility unless explicitly changed.
14. No silent architecture changes.
15. No unnecessary microservices.
16. No premature infrastructure complexity.
17. No scope creep.
18. No fake PASS.
19. No hardcoded secrets.
20. No production-risky shortcuts.

---

# 5. ARCHITECTURE CONTRACT

The existing architecture MUST be reused.

Before creating a new subsystem, Jules MUST search the repository for existing functionality.

Feature mapping:

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
