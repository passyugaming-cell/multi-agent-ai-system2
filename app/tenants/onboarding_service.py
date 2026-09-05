import uuid
from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.database.models.onboarding import OnboardingChecklist
from app.core.exceptions import TenantNotFoundException, AppException
from app.tenants.lifecycle import ClientLifecycleManager
from app.tenants.provisioning.provisioner import TenantProvisioner
from app.tenants.provisioning.validators import TenantValidatorEngine
from app.tenants.provisioning.readiness import ReadinessCalculator
from app.tenants.provisioning.exceptions import ChecklistRequirementError, ReadinessValidationError
from app.tenants.provisioning.schemas import (
    OnboardingSummaryResponse,
    ChecklistSummary,
    ChecklistItemResponse,
    ChecklistItemUpdate,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class OnboardingService:
    """Service layer for tenant onboarding management, checklists, and readiness validation."""

    def __init__(self, session: AsyncSession):
        self.session = session
        self.lifecycle_manager = ClientLifecycleManager(session)
        self.provisioner = TenantProvisioner(session)

    async def start_onboarding(self, tenant_id: uuid.UUID) -> OnboardingSummaryResponse:
        """Starts tenant onboarding flow."""
        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.session.execute(tenant_stmt)).scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundException()

        if tenant.lifecycle_state == "PROSPECT":
            await self.lifecycle_manager.transition_state(
                tenant_id=tenant_id,
                target_state="ONBOARDING",
                reason="Onboarding process started by client",
            )

        # Run provisioner to ensure default templates exist and are initialized
        await self.provisioner.provision_tenant(tenant_id)
        return await self.get_onboarding_summary(tenant_id)

    async def get_onboarding_summary(self, tenant_id: uuid.UUID) -> OnboardingSummaryResponse:
        """Get summary of onboarding checklist, readiness score, and blocking items."""
        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.session.execute(tenant_stmt)).scalar_one_or_none()
        if not tenant:
            raise TenantNotFoundException()

        cl_stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tenant_id)
        checklist_items = (await self.session.execute(cl_stmt)).scalars().all()

        if not checklist_items:
            # Provision if not initialized
            await self.provisioner.provision_tenant(tenant_id)
            checklist_items = (await self.session.execute(cl_stmt)).scalars().all()

        val_results = await TenantValidatorEngine(self.session).validate_all(tenant_id)
        readiness = ReadinessCalculator.calculate(checklist_items, val_results)

        completed_count = len(readiness.completed_requirements)
        total_count = len(checklist_items)
        pending_count = total_count - completed_count

        summary = ChecklistSummary(
            total=total_count,
            completed=completed_count,
            pending=pending_count,
            completion_percentage=round((completed_count / total_count * 100) if total_count > 0 else 0.0, 2),
        )

        warnings: list[str] = []
        if readiness.blocking_requirements:
            warnings.append(f"Incomplete blocking requirements: {', '.join(readiness.blocking_requirements)}")

        item_responses = [ChecklistItemResponse.model_validate(item) for item in checklist_items]

        return OnboardingSummaryResponse(
            tenant_id=tenant_id,
            lifecycle_state=tenant.lifecycle_state,
            readiness_score=readiness.score,
            readiness_status=readiness.readiness_status,
            checklist_summary=summary,
            checklist_items=item_responses,
            blocking_items=readiness.blocking_requirements,
            warnings=warnings,
        )

    async def get_checklist(self, tenant_id: uuid.UUID) -> list[ChecklistItemResponse]:
        """List all checklist items for a tenant."""
        cl_stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tenant_id)
        items = (await self.session.execute(cl_stmt)).scalars().all()
        return [ChecklistItemResponse.model_validate(item) for item in items]

    async def update_checklist_item(
        self, tenant_id: uuid.UUID, item_id: uuid.UUID, update_data: ChecklistItemUpdate
    ) -> ChecklistItemResponse:
        """Update a checklist item's status, enforcing tenant isolation and required constraints."""
        cl_stmt = select(OnboardingChecklist).where(
            OnboardingChecklist.tenant_id == tenant_id,
            OnboardingChecklist.id == item_id,
        )
        item = (await self.session.execute(cl_stmt)).scalar_one_or_none()
        if not item:
            raise AppException(code="CHECKLIST_ITEM_NOT_FOUND", message="Checklist item not found", status_code=404)

        if update_data.status:
            status_upper = update_data.status.upper()
            if status_upper == "SKIPPED" and item.required:
                raise ChecklistRequirementError("Required checklist items cannot be skipped")

            item.status = status_upper
            if status_upper == "COMPLETED":
                item.completion_percentage = 100.0
                item.completed_at = utc_now()
            elif status_upper == "PENDING":
                item.completion_percentage = 0.0
                item.completed_at = None

        if update_data.completion_percentage is not None:
            item.completion_percentage = update_data.completion_percentage

        if update_data.metadata_info is not None:
            item.metadata_info = update_data.metadata_info

        await self.session.flush()
        await self.session.refresh(item)
        return ChecklistItemResponse.model_validate(item)

    async def validate_onboarding(self, tenant_id: uuid.UUID) -> OnboardingSummaryResponse:
        """Runs validation checks, updates checklist items, and updates readiness score."""
        val_results = await TenantValidatorEngine(self.session).validate_all(tenant_id)

        cl_stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tenant_id)
        checklist_items = (await self.session.execute(cl_stmt)).scalars().all()

        for item in checklist_items:
            is_valid = val_results.get(item.key, False)
            if is_valid:
                item.status = "COMPLETED"
                item.completion_percentage = 100.0
                if not item.completed_at:
                    item.completed_at = utc_now()

        await self.session.flush()

        readiness = ReadinessCalculator.calculate(checklist_items, val_results)
        tenant_stmt = select(Tenant).where(Tenant.id == tenant_id)
        tenant = (await self.session.execute(tenant_stmt)).scalar_one_or_none()

        if tenant and readiness.readiness_status == "READY":
            await self.lifecycle_manager.transition_state(
                tenant_id=tenant_id,
                target_state="READY",
                reason="Onboarding validation passed minimum readiness score >= 90%",
            )

        return await self.get_onboarding_summary(tenant_id)

    async def complete_onboarding(self, tenant_id: uuid.UUID) -> OnboardingSummaryResponse:
        """Complete onboarding and transition tenant to READY if readiness conditions are satisfied."""
        summary = await self.get_onboarding_summary(tenant_id)
        if summary.readiness_status != "READY" or summary.blocking_items:
            raise ReadinessValidationError(
                f"Cannot complete onboarding: Readiness score is {summary.readiness_score}% "
                f"and blocking items remain: {summary.blocking_items}"
            )

        await self.lifecycle_manager.transition_state(
            tenant_id=tenant_id,
            target_state="READY",
            reason="Onboarding explicitly completed with readiness score >= 90%",
        )

        return await self.get_onboarding_summary(tenant_id)
