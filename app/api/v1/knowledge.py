from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.core.auth import resolve_actor_permissions
from app.database.session import get_db_session
from app.tenants.business_service import BusinessDataService
from app.schemas.domain import (
    KnowledgeItemCreate,
    KnowledgeItemUpdate,
    KnowledgeItemResponse,
    KnowledgeItemApproveRequest,
)

router = APIRouter(prefix="/knowledge", tags=["Knowledge Base & Policies"])


def _get_tenant_id_or_400() -> UUID:
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID context missing or invalid.",
        )
    return tenant_id


@router.get("", response_model=list[KnowledgeItemResponse])
async def list_knowledge_items(
    category_key: str | None = Query(None),
    status_filter: str | None = Query(None, alias="status"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.list_knowledge_items(
        tenant_id,
        category_key=category_key,
        status=status_filter,
        skip=skip,
        limit=limit,
        actor_permissions=actor_permissions,
    )


@router.post("", response_model=KnowledgeItemResponse, status_code=status.HTTP_201_CREATED)
async def create_knowledge_item(
    payload: KnowledgeItemCreate,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.create_knowledge_item(tenant_id, payload, actor_permissions=actor_permissions)


@router.get("/{item_id}", response_model=KnowledgeItemResponse)
async def get_knowledge_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.get_knowledge_item(tenant_id, item_id, actor_permissions=actor_permissions)


@router.put("/{item_id}", response_model=KnowledgeItemResponse)
async def update_knowledge_item(
    item_id: UUID,
    payload: KnowledgeItemUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.update_knowledge_item(tenant_id, item_id, payload, actor_permissions=actor_permissions)


@router.delete("/{item_id}", response_model=KnowledgeItemResponse)
async def archive_knowledge_item(
    item_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.archive_knowledge_item(tenant_id, item_id, actor_permissions=actor_permissions)


@router.post("/{item_id}/approve", response_model=KnowledgeItemResponse)
async def approve_knowledge_item(
    item_id: UUID,
    payload: KnowledgeItemApproveRequest = KnowledgeItemApproveRequest(),
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.approve_knowledge_item(
        tenant_id,
        item_id,
        approved_by=payload.approved_by,
        reason=payload.reason,
        actor_permissions=actor_permissions,
    )


@router.post("/{item_id}/archive", response_model=KnowledgeItemResponse)
async def archive_knowledge_item_alias(
    item_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.archive_knowledge_item(tenant_id, item_id, actor_permissions=actor_permissions)
