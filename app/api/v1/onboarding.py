import uuid
from fastapi import APIRouter, Depends, Header
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_context
from app.core.exceptions import AppException
from app.database.session import get_db
from app.tenants.lifecycle import ClientLifecycleManager
from app.tenants.onboarding_service import OnboardingService
from app.tenants.provisioning.provisioner import TenantProvisioner
from app.tenants.provisioning.schemas import (
    ProvisioningResponse,
    OnboardingSummaryResponse,
    ChecklistItemResponse,
    ChecklistItemUpdate,
    LifecycleTransitionRequest,
    LifecycleTransitionResponse,
)

router = APIRouter(tags=["Tenant Onboarding & Provisioning"])


def verify_tenant_authorization(tenant_id: uuid.UUID) -> None:
    """Enforces strict tenant isolation by matching path parameter with tenant context."""
    context_id = get_tenant_context()
    if not context_id or str(context_id) != str(tenant_id):
        raise AppException(
            code="FORBIDDEN_CROSS_TENANT_ACCESS",
            message="Cross-tenant access prohibited",
            status_code=403,
        )


# --- PROVISIONING ENDPOINTS ---

@router.post("/tenants/provision", response_model=ProvisioningResponse)
async def provision_current_tenant(
    db: AsyncSession = Depends(get_db),
) -> ProvisioningResponse:
    """Provision configuration for the current active tenant (from X-Tenant-ID context)."""
    context_id = get_tenant_context()
    if not context_id:
        raise AppException(code="MISSING_TENANT_HEADER", message="Tenant context not found", status_code=400)

    provisioner = TenantProvisioner(db)
    return await provisioner.provision_tenant(context_id)


@router.post("/tenants/{tenant_id}/provision", response_model=ProvisioningResponse)
async def provision_tenant_by_id(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> ProvisioningResponse:
    """Provision configuration for a specific tenant_id, enforcing tenant isolation."""
    verify_tenant_authorization(tenant_id)
    provisioner = TenantProvisioner(db)
    return await provisioner.provision_tenant(tenant_id)


# --- ONBOARDING ENDPOINTS ---

@router.post("/tenants/{tenant_id}/onboarding/start", response_model=OnboardingSummaryResponse)
async def start_onboarding(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> OnboardingSummaryResponse:
    """Start onboarding flow for a tenant."""
    verify_tenant_authorization(tenant_id)
    service = OnboardingService(db)
    return await service.start_onboarding(tenant_id)


@router.get("/tenants/{tenant_id}/onboarding", response_model=OnboardingSummaryResponse)
async def get_onboarding_summary(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> OnboardingSummaryResponse:
    """Retrieve onboarding summary and readiness status for a tenant."""
    verify_tenant_authorization(tenant_id)
    service = OnboardingService(db)
    return await service.get_onboarding_summary(tenant_id)


@router.get("/tenants/{tenant_id}/onboarding/checklist", response_model=list[ChecklistItemResponse])
async def get_onboarding_checklist(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ChecklistItemResponse]:
    """Retrieve all checklist items for a tenant."""
    verify_tenant_authorization(tenant_id)
    service = OnboardingService(db)
    return await service.get_checklist(tenant_id)


@router.patch("/tenants/{tenant_id}/onboarding/checklist/{item_id}", response_model=ChecklistItemResponse)
async def update_checklist_item(
    tenant_id: uuid.UUID,
    item_id: uuid.UUID,
    payload: ChecklistItemUpdate,
    db: AsyncSession = Depends(get_db),
) -> ChecklistItemResponse:
    """Update status or completion percentage of a checklist item."""
    verify_tenant_authorization(tenant_id)
    service = OnboardingService(db)
    return await service.update_checklist_item(tenant_id, item_id, payload)


@router.post("/tenants/{tenant_id}/onboarding/validate", response_model=OnboardingSummaryResponse)
async def validate_onboarding(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> OnboardingSummaryResponse:
    """Trigger deterministic validation checks on tenant database configuration."""
    verify_tenant_authorization(tenant_id)
    service = OnboardingService(db)
    return await service.validate_onboarding(tenant_id)


@router.post("/tenants/{tenant_id}/onboarding/complete", response_model=OnboardingSummaryResponse)
async def complete_onboarding(
    tenant_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
) -> OnboardingSummaryResponse:
    """Complete onboarding and mark tenant as READY if score >= 90% and no blocking items."""
    verify_tenant_authorization(tenant_id)
    service = OnboardingService(db)
    return await service.complete_onboarding(tenant_id)


# --- LIFECYCLE TRANSITION ENDPOINT ---

@router.post("/tenants/{tenant_id}/lifecycle/transition", response_model=LifecycleTransitionResponse)
async def transition_lifecycle_state(
    tenant_id: uuid.UUID,
    payload: LifecycleTransitionRequest,
    db: AsyncSession = Depends(get_db),
) -> LifecycleTransitionResponse:
    """Transition tenant lifecycle state explicitly with rule validation."""
    verify_tenant_authorization(tenant_id)
    mgr = ClientLifecycleManager(db)
    tenant = await mgr.transition_state(
        tenant_id=tenant_id,
        target_state=payload.target_state,
        reason=payload.reason,
        actor="api_user",
    )
    return LifecycleTransitionResponse(
        tenant_id=tenant.id,
        previous_state=tenant.previous_state,
        current_state=tenant.lifecycle_state,
        transition_timestamp=tenant.state_transition_at or tenant.updated_at,
        transition_reason=tenant.transition_reason,
    )
