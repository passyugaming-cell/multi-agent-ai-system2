# AI BOS R3 — DATABASE AND EXTERNAL SIDE-EFFECT BOUNDARY ARCHITECTURE & SEMANTICS

**Version:** 1.0
**Author:** AI BOS System Engineering
**Scope:** R3 WhatsApp Subsystem & Outbound External Integration Execution

---

## 1. Executive Summary & Core Principle

In distributed systems, a relational database transaction (e.g., PostgreSQL / SQLAlchemy transaction) **cannot** atomically encompass an external HTTP API side-effect (e.g., Meta WhatsApp Cloud API endpoint call). An HTTP call cannot be rolled back if the SQL transaction subsequently fails, nor can an HTTP provider's internal state be guaranteed prior to network response processing.

To eliminate "outbound false success" (R3-001) and "outbound retry duplication" (R3-009), AI BOS explicitly decouples internal database message state management from external provider execution using an explicit, state-machine-driven side-effect boundary.

---

## 2. Message State Machine & Lifecycle Transitions

All outbound `Message` entities follow a deterministic 7-state lifecycle governed by `validate_message_status_transition`:

```
                 ┌──────────────┐
                 │   CREATED    │
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │    QUEUED    │
                 └──────┬───────┘
                        │
                        ▼
                 ┌──────────────┐
                 │   SENDING    │
                 └──────┬───────┘
                        │
        ┌───────────────┼───────────────┐
        │ (Success)     │ (Definitive)  │ (Timeout / Ambiguous)
        ▼               ▼               ▼
┌──────────────┐ ┌──────────────┐ ┌──────────────┐
│     SENT     │ │    FAILED    │ │   UNKNOWN    │
└──────┬───────┘ └──────────────┘ └──────────────┘
       │ (Webhook)
       ▼
┌──────────────┐
│  DELIVERED   │
└──────┬───────┘
       │ (Webhook)
       ▼
┌──────────────┐
│     READ     │
└──────────────┘
```

---

## 3. Explicit Side-Effect Boundary & Failure Window Matrix

The table below documents the exact behavior, internal DB status, event publication policy, and failure window semantics for every possible outbound execution scenario:

| Scenario | Provider Execution Outcome | Database `Message.status` | EventBus Publication (`whatsapp.message_sent`) | Retry Policy | Failure Window / Recovery Semantics |
|---|---|---|---|---|---|
| **Case A: Provider Success** | `OperationExecutionResult.status == 'COMPLETED'` with valid `provider_message_id` | `SENT` | **PUBLISHED** | None required | Fully committed. External side-effect and internal DB status are aligned. |
| **Case B: Definitive Rejection** | Provider explicitly rejects HTTP request (e.g., 4xx invalid recipient, 400 bad payload) or `status == 'FAILED'` | `FAILED` | **SUPPRESSED** (Never published) | Non-retryable | Prevents false outbound claims. Internal status reflects terminal failure. |
| **Case C: Ambiguous Network Timeout** | HTTP client timeout (`TimeoutError`, `httpx.TimeoutException`) or connection drop during socket wait | `UNKNOWN` | **SUPPRESSED** (Never published) | **NO BLIND RETRY** (`effective_retries=1`) | **Ambiguous Window:** The provider may or may not have dispatched the message. System preserves uncertainty as `UNKNOWN`. Blind retries are strictly prohibited to prevent duplicate messages to customers. Re-reconciliation occurs via status webhook or administrative audit. |
| **Case D: Provider Success + Local DB Commit Failure** | Provider returned `200 OK` with `provider_message_id`, but subsequent local SQL transaction fails during commit | Rollback | **SUPPRESSED** | Re-reconciled via status webhook | **Post-Execution Window:** Customer receives message on WhatsApp. External status webhook arriving later for `provider_message_id` resolves customer context or records orphan execution safely. |
| **Case E: DB Success + EventBus Publication Failure** | Local DB status committed as `SENT`, but EventBus emission raises an exception | `SENT` | Failed emission | Audit log | **Post-Commit Window:** Database truth (`SENT`) remains authoritative. Event bus failure is logged for background replay without corrupting message state. |
| **Case F: Human Takeover Suppression** | Router detects human ownership (`WAITING_HUMAN`, `HUMAN_ACTIVE`, `CLOSED`) before outbound dispatch | `FAILED` | **SUPPRESSED** | N/A | AI generation output is discarded without invoking external provider API. Customer receives zero AI responses after human takeover. |

---

## 4. Single-Invocation Outbound Enforcement (`effective_retries=1`)

To prevent duplicate customer messages resulting from ambiguous HTTP timeouts, `IntegrationService.execute_operation` strictly caps retry attempts for non-idempotent outbound send operations (`send_message`, `send_whatsapp`, `send_email`, `send_sms`):

```python
# Non-idempotent operations like outbound message sends must NOT be retried blindly upon ambiguous failure/timeout
effective_retries = 1 if operation in ("send_message", "send_whatsapp", "send_email", "send_sms") else 3
res = await execute_with_retry(_run, max_retries=effective_retries)
```

If the HTTP request times out, `execute_operation` raises the timeout exception immediately on the first attempt, allowing the webhook handler to transition `Message.status` directly from `SENDING` to `UNKNOWN`.

---

## 5. Persistent Audit Trail for Invalid Transitions

When a provider webhook emits an out-of-order or invalid status event (e.g., `delivered` event for a message in `CREATED` status), the state machine rejects the transition. Rather than discarding the event or corrupting `Message.status`, the system persists an `IntegrationExecution` audit record:

- `status`: `"FAILED"`
- `error_code`: `"INVALID_STATUS_TRANSITION"`
- `safe_error_message`: `"Could not transition message status to DELIVERED"`
- `response_payload`: `{"status": "delivered", "rejected": True}`

The original `Message.status` remains untouched (`CREATED`), guaranteeing total database state integrity.
