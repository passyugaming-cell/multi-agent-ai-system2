import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.database.models.audit import ProvisioningAudit
from app.database.models.onboarding import OnboardingChecklist
from app.core.exceptions import TenantNotFoundException
from app.tenants.provisioning.exceptions import InvalidLifecycleTransitionError
from app.tenants.provisioning.readiness import ReadinessCalculator
from app.tenants.provisioning.validators import TenantValidatorEngine

VALID_LIFECYCLE_STATES = {
    "PROSPECT",
    "ONBOARDING",
    "CONFIGURING",
    "VALIDATING",
    "READY",
    "ACTIVE",
    "BLOCKED",
    "SUSPENDED",
    "ARCHIVED",
}

# Explicit Allowed Transitions: map current state -> set of allowed next states
ALLOWED_TRANSITIONS = {
    "PROSPECT": {"ONBOARDING", "CONFIGURING", "BLOCKED", "ARCHIVED"},
    "ONBOARDING": {"CONFIGURING", "VALIDATING", "BLOCKED", "ARCHIVED"},
    "CONFIGURING": {"VALIDATING", "READY", "ONBOARDING", "BLOCKED", "ARCHIVED"},
    "VALIDATING": {"READY", "CONFIGURING", "BLOCKED", "ARCHIVED"},
    "READY": {"ACTIVE", "CONFIGURING", "SUSPENDED", "BLOCKED", "ARCHIVED"},
    "ACTIVE": {"SUSPENDED", "BLOCKED", "ARCHIVED"},
    "BLOCKED": {"ONBOARDING", "CONFIGURING", "VALIDATING", "READY", "ARCHIVED"},
    "SUSPENDED": {"READY", "ACTIVE", "BLOCKED", "ARCHIVED"},
    "ARCHIVED": set(),  # Terminal state
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ClientLifecycleManager:
    """Manages ClientLifecycle state machine and transition validation."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def transition_state(
        self,
        tenant_id: uuid.UUID,
        target_state: str,
        reason: str | None = None,
        actor: str = "system",
    ) -> Tenant:
        """Transitions tenant to target_state after validating transition rules."""
        target_state = target_state.upper()
        if target_state not in VALID_LIFECYCLE_STATES:
            raise InvalidLifecycleTransitionError("UNKNOWN", target_state, f"State '{target_state}' is invalid")

        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.session.execute(tenant_stmt)).scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundException()

        current_state = tenant.lifecycle_state.upper()

        if current_state == target_state:
            # Idempotent state transition
            return tenant

        allowed = ALLOWED_TRANSITIONS.get(current_state, set())
        if target_state not in allowed:
            raise InvalidLifecycleTransitionError(
                current_state,
                target_state,
                f"Transition from '{current_state}' to '{target_state}' is not permitted.",
            )

        # Transition specific readiness validations
        if target_state == "READY":
            # Must pass readiness score check >= 90% and no blocking items
            validator = TenantValidatorEngine(self.session)
            val_results = await validator.validate_all(tenant_id)
            cl_stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tenant_id)
            cls = (await self.session.execute(cl_stmt)).scalars().all()
            readiness = ReadinessCalculator.calculate(cls, val_results)

            if readiness.readiness_status != "READY":
                raise InvalidLifecycleTransitionError(
                    current_state,
                    target_state,
                    f"Readiness score is {readiness.score}% with blocking items: {readiness.blocking_requirements}",
                )

        if target_state == "ACTIVE":
            if current_state not in ("READY", "SUSPENDED"):
                raise InvalidLifecycleTransitionError(
                    current_state,
                    target_state,
                    "Tenant must be in READY or SUSPENDED state prior to becoming ACTIVE.",
                )

        # Perform transition
        tenant.previous_state = current_state
        tenant.lifecycle_state = target_state
        tenant.state_transition_at = utc_now()
        tenant.transition_reason = reason or f"State transitioned to {target_state}"

        # Audit log
        audit = ProvisioningAudit(
            tenant_id=tenant_id,
            action="LIFECYCLE_TRANSITION",
            previous_state=current_state,
            new_state=target_state,
            actor=actor,
            reason=reason or f"Transitioned from {current_state} to {target_state}",
            result="SUCCESS",
        )
        self.session.add(audit)
        await self.session.flush()

        return tenant
