from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.repositories.domain import BusinessProfileRepository
from app.schemas.domain import (
    BusinessProfileCreate,
    BusinessProfileUpdate,
    BusinessProfileResponse,
)

router = APIRouter(prefix="/business-profile", tags=["Business Profile"])


def _get_tenant_id_or_400() -> UUID:
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID context missing or invalid.",
        )
    return tenant_id


@router.get("", response_model=BusinessProfileResponse)
async def get_business_profile(
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = _get_tenant_id_or_400()
    repo = BusinessProfileRepository(db)
    profile = await repo.get_by_tenant(tenant_id)
    if not profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business profile not found for tenant.",
        )
    return profile


@router.post("", response_model=BusinessProfileResponse, status_code=status.HTTP_201_CREATED)
async def create_or_update_business_profile(
    payload: BusinessProfileCreate,
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = _get_tenant_id_or_400()
    repo = BusinessProfileRepository(db)
    existing = await repo.get_by_tenant(tenant_id)

    if existing:
        updated = await repo.update(
            tenant_id, existing.id, **payload.model_dump(exclude_unset=True)
        )
        await db.commit()
        return updated
    else:
        created = await repo.create(tenant_id, **payload.model_dump())
        await db.commit()
        return created
