from uuid import UUID
from typing import Sequence
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.core.auth import resolve_actor_permissions
from app.database.session import get_db_session
from app.tenants.business_service import BusinessDataService
from app.schemas.domain import (
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    ProductVariantCreate,
    ProductVariantUpdate,
    ProductVariantResponse,
)

router = APIRouter(prefix="/products", tags=["Products & Catalog"])


def _get_tenant_id_or_400() -> UUID:
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID context missing or invalid.",
        )
    return tenant_id


@router.get("", response_model=list[ProductResponse])
async def list_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.list_products(tenant_id, skip=skip, limit=limit, actor_permissions=actor_permissions)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.create_product(tenant_id, payload, actor_permissions=actor_permissions)


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.get_product(tenant_id, product_id, actor_permissions=actor_permissions)


@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: UUID,
    payload: ProductUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.update_product(tenant_id, product_id, payload, actor_permissions=actor_permissions)


@router.delete("/{product_id}", status_code=status.HTTP_200_OK)
async def delete_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    await service.delete_product(tenant_id, product_id, actor_permissions=actor_permissions)
    return {"message": "Product deleted successfully", "id": str(product_id)}


@router.post("/{product_id}/variants", response_model=ProductVariantResponse, status_code=status.HTTP_201_CREATED)
async def create_product_variant(
    product_id: UUID,
    payload: ProductVariantCreate,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.create_product_variant(tenant_id, product_id, payload, actor_permissions=actor_permissions)


@router.put("/variants/{variant_id}", response_model=ProductVariantResponse)
async def update_product_variant(
    variant_id: UUID,
    payload: ProductVariantUpdate,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    return await service.update_product_variant(tenant_id, variant_id, payload, actor_permissions=actor_permissions)


@router.delete("/variants/{variant_id}", status_code=status.HTTP_200_OK)
async def delete_product_variant(
    variant_id: UUID,
    db: AsyncSession = Depends(get_db_session),
    actor_permissions: set[str] = Depends(resolve_actor_permissions),
):
    tenant_id = _get_tenant_id_or_400()
    service = BusinessDataService(db)
    await service.delete_product_variant(tenant_id, variant_id, actor_permissions=actor_permissions)
    return {"message": "Variant deleted successfully", "id": str(variant_id)}
