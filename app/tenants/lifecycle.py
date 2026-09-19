import logging
from enum import Enum
from typing import Optional, Set, Any
from app.core.exceptions import AppException
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.tenant import Tenant
from app.database.models.billing import Subscription
from app.billing.subscription import SubscriptionService
from app.core.context import get_actor_context

logger = logging.getLogger(__name__)


class ClientLifecycleManager:
    """Manager for tenant lifecycle transitions and activation gate enforcement."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.subscription_service = SubscriptionService(db)

    async def transition_state(
        self,
        tenant_id: uuid.UUID,
        target_state: str,
        reason: str | None = None,
        actor: str | None = None,
    ) -> Tenant:
        stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.db.execute(stmt)).scalar_one_or_none()
        if not tenant:
            raise AppException(code="TENANT_NOT_FOUND", message="Tenant not found.", status_code=404)

        current_state = tenant.lifecycle_state or "PROSPECT"
        active_actor = get_actor_context()

        # Resolve subscription & readiness score context for activation gate
        from app.tenants.onboarding_service import OnboardingService
        onboarding_service = OnboardingService(self.db)

        subscription = await self.subscription_service.get_subscription_or_none(tenant_id)
        readiness_summary = await onboarding_service.get_onboarding_summary(tenant_id)
        readiness_score = readiness_summary.readiness

        validate_tenant_lifecycle_transition(
            current_state=current_state,
            target_state=target_state,
            tenant=tenant,
            subscription=subscription,
            readiness_score=readiness_score,
            actor=active_actor,
        )

        now = datetime.now(timezone.utc)
        tenant.previous_state = current_state
        tenant.lifecycle_state = target_state
        tenant.state_transition_at = now
        tenant.transition_reason = reason or f"Transitioned by {actor or 'system'}"

        await self.db.commit()
        await self.db.refresh(tenant)
        return tenant


class TenantLifecycleState(str, Enum):
    PROSPECT = "PROSPECT"
    LEAD = "LEAD"
    QUALIFIED = "QUALIFIED"
    PROPOSAL = "PROPOSAL"
    WAITING_PAYMENT = "WAITING_PAYMENT"
    PAID = "PAID"
    CLIENT = "CLIENT"
    ONBOARDING = "ONBOARDING"
    CONFIGURING = "CONFIGURING"
    TESTING = "TESTING"
    READY = "READY"
    ACTIVE = "ACTIVE"
    BLOCKED = "BLOCKED"
    WAITING_OWNER = "WAITING_OWNER"
    WAITING_CLIENT = "WAITING_CLIENT"
    ERROR = "ERROR"
    PAUSED = "PAUSED"
    STALE = "STALE"


ALLOWED_TENANT_LIFECYCLE_TRANSITIONS: dict[TenantLifecycleState, Set[TenantLifecycleState]] = {
    TenantLifecycleState.PROSPECT: {
        TenantLifecycleState.LEAD,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.LEAD: {
        TenantLifecycleState.QUALIFIED,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.QUALIFIED: {
        TenantLifecycleState.PROPOSAL,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.PROPOSAL: {
        TenantLifecycleState.WAITING_PAYMENT,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.WAITING_PAYMENT: {
        TenantLifecycleState.PAID,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.PAID: {
        TenantLifecycleState.CLIENT,
        TenantLifecycleState.ONBOARDING,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.CLIENT: {
        TenantLifecycleState.ONBOARDING,
        TenantLifecycleState.PAUSED,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.ONBOARDING: {
        TenantLifecycleState.CONFIGURING,
        TenantLifecycleState.PAUSED,
        TenantLifecycleState.STALE,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.CONFIGURING: {
        TenantLifecycleState.TESTING,
        TenantLifecycleState.PAUSED,
        TenantLifecycleState.STALE,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.TESTING: {
        TenantLifecycleState.READY,
        TenantLifecycleState.CONFIGURING,
        TenantLifecycleState.PAUSED,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.READY: {
        TenantLifecycleState.ACTIVE,
        TenantLifecycleState.TESTING,
        TenantLifecycleState.PAUSED,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.ACTIVE: {
        TenantLifecycleState.PAUSED,
        TenantLifecycleState.BLOCKED,
        TenantLifecycleState.STALE,
        TenantLifecycleState.ERROR,
    },
    TenantLifecycleState.PAUSED: {
        TenantLifecycleState.ONBOARDING,
        TenantLifecycleState.CONFIGURING,
        TenantLifecycleState.TESTING,
        TenantLifecycleState.READY,
        TenantLifecycleState.ACTIVE,
        TenantLifecycleState.BLOCKED,
    },
    TenantLifecycleState.STALE: {
        TenantLifecycleState.ONBOARDING,
        TenantLifecycleState.PAUSED,
        TenantLifecycleState.BLOCKED,
    },
    TenantLifecycleState.BLOCKED: {
        TenantLifecycleState.PROSPECT,
        TenantLifecycleState.ONBOARDING,
        TenantLifecycleState.CONFIGURING,
        TenantLifecycleState.TESTING,
        TenantLifecycleState.READY,
        TenantLifecycleState.ACTIVE,
    },
    TenantLifecycleState.ERROR: {
        TenantLifecycleState.PROSPECT,
        TenantLifecycleState.ONBOARDING,
        TenantLifecycleState.CONFIGURING,
        TenantLifecycleState.TESTING,
        TenantLifecycleState.READY,
        TenantLifecycleState.ACTIVE,
    },
    TenantLifecycleState.WAITING_OWNER: {
        TenantLifecycleState.ONBOARDING,
        TenantLifecycleState.CONFIGURING,
        TenantLifecycleState.READY,
        TenantLifecycleState.PAUSED,
        TenantLifecycleState.BLOCKED,
    },
    TenantLifecycleState.WAITING_CLIENT: {
        TenantLifecycleState.ONBOARDING,
        TenantLifecycleState.CONFIGURING,
        TenantLifecycleState.READY,
        TenantLifecycleState.PAUSED,
        TenantLifecycleState.BLOCKED,
    },
}


def validate_tenant_lifecycle_transition(
    current_state: str,
    target_state: str,
    tenant: Tenant,
    subscription: Optional[Subscription] = None,
    readiness_score: Optional[Any] = None,
    actor: Optional[Any] = None,
) -> None:
    """Validates tenant lifecycle state transition according to S-001 specification rules."""
    if current_state == target_state:
        return

    try:
        curr_enum = TenantLifecycleState(current_state)
    except ValueError:
        curr_enum = None

    try:
        target_enum = TenantLifecycleState(target_state)
    except ValueError:
        raise AppException(
            code="INVALID_TENANT_LIFECYCLE_TRANSITION",
            message=f"Unknown target tenant lifecycle state: '{target_state}'.",
            status_code=400,
        )

    # Recovery from ERROR or BLOCKED requires Platform Owner authority
    if curr_enum in (TenantLifecycleState.ERROR, TenantLifecycleState.BLOCKED):
        is_platform_owner = actor and getattr(actor, "is_platform_owner", False)
        if not is_platform_owner:
            raise AppException(
                code="PERMISSION_DENIED",
                message=f"Recovery from {curr_enum.value} state requires Platform Owner authority.",
                status_code=403,
            )

    if curr_enum:
        allowed = ALLOWED_TENANT_LIFECYCLE_TRANSITIONS.get(curr_enum, set())
        if target_enum not in allowed:
            logger.warning(
                "Rejected invalid tenant lifecycle transition: '%s' -> '%s' for tenant %s",
                current_state,
                target_state,
                tenant.id,
            )
            raise AppException(
                code="INVALID_TENANT_LIFECYCLE_TRANSITION",
                message=f"Cannot transition tenant lifecycle state from '{current_state}' to '{target_state}'.",
                status_code=400,
            )

    # Activation Gate Enforcement for transition to ACTIVE
    if target_enum == TenantLifecycleState.ACTIVE:
        if readiness_score is None:
            raise AppException(
                code="TENANT_ACTIVATION_GATE_FAILED",
                message="Tenant activation blocked: Readiness score evaluation is required.",
                status_code=400,
            )
        r_status = getattr(readiness_score, "readiness_status", None)
        if r_status != "READY":
            raise AppException(
                code="TENANT_ACTIVATION_GATE_FAILED",
                message=f"Tenant activation blocked: Readiness status is '{r_status}', must be 'READY'.",
                status_code=400,
            )

        if subscription is None:
            raise AppException(
                code="TENANT_ACTIVATION_GATE_FAILED",
                message="Tenant activation blocked: Subscription record is required.",
                status_code=400,
            )
        sub_status = getattr(subscription, "status", None)
        if sub_status not in ("TRIALING", "ACTIVE"):
            raise AppException(
                code="TENANT_ACTIVATION_GATE_FAILED",
                message=f"Tenant activation blocked: Subscription status is '{sub_status}', must be 'TRIALING' or 'ACTIVE'.",
                status_code=400,
            )

        sub_amount = getattr(subscription, "amount", 0)
        if sub_amount and float(sub_amount) > 0:
            meta = getattr(subscription, "metadata_", {}) or {}
            if not meta.get("verified_payment"):
                raise AppException(
                    code="PAYMENT_VERIFICATION_REQUIRED",
                    message="Tenant activation blocked: Verified payment is required for paid subscriptions.",
                    status_code=402,
                )
