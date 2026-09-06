from uuid import UUID
from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.tenants.business_service import BusinessDataService
from app.tenants.provisioning.validators import TenantValidatorEngine
from app.tenants.provisioning.readiness import ReadinessCalculator
from app.database.models.onboarding import OnboardingChecklist
from app.schemas.domain import (
    BusinessProfileCreate,
    BusinessProfileUpdate,
    BusinessProfileResponse,
)

router = APIRouter(prefix="/business", tags=["Business Setup"])


def _get_tenant_id_or_400() -> UUID:
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID context missing or invalid.",
        )
    return tenant_id


def _get_actor_permissions(x_actor_permissions: str | None = Header(None, alias="X-Actor-Permissions")) -> set[str] | None:
    if x_actor_permissions is None:
        return None
    return set(p.strip() for p in x_actor_permissions.split(",") if p.strip())


@router.get("", response_model=BusinessProfileResponse)
async def get_business(
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] | None = Depends(_get_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.get_business_profile(tenant_id, actor_permissions=actor_permissions)


@router.put("", response_model=BusinessProfileResponse)
@router.post("", response_model=BusinessProfileResponse, status_code=status.HTTP_200_OK)
async def update_business(
    payload: BusinessProfileUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] | None = Depends(_get_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.create_or_update_business_profile(tenant_id, payload, actor_permissions=actor_permissions)


@router.get("/readiness")
async def get_business_readiness(
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = _get_tenant_id_or_400()
    validator = TenantValidatorEngine(db)
    validation_results = await validator.validate_all(tenant_id)

    checklist_stmt = select(OnboardingChecklist).where(OnboardingChecklist.tenant_id == tenant_id)
    items = (await db.execute(checklist_stmt)).scalars().all()

    readiness = ReadinessCalculator.calculate(items, validation_results)
    return {
        "ready": readiness.readiness_status == "READY",
        "readiness_status": readiness.readiness_status,
        "score": readiness.score,
        "percentage": readiness.percentage,
        "completed_requirements": readiness.completed_requirements,
        "incomplete_requirements": readiness.incomplete_requirements,
        "blocking_requirements": readiness.blocking_requirements,
        "category_scores": readiness.category_scores,
    }
