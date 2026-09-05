from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.repositories.domain import ProductRepository
from app.schemas.domain import ProductCreate, ProductUpdate, ProductResponse

router = APIRouter(prefix="/products", tags=["Products"])


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
):
    tenant_id = _get_tenant_id_or_400()
    repo = ProductRepository(db)
    return await repo.list_all(tenant_id=tenant_id, skip=skip, limit=limit)


@router.post("", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    payload: ProductCreate,
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = _get_tenant_id_or_400()
    repo = ProductRepository(db)
    data = payload.model_dump()
    if "metadata" in data:
        data["metadata_"] = data.pop("metadata")
    product = await repo.create(tenant_id=tenant_id, **data)
    await db.commit()
    return product


@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = _get_tenant_id_or_400()
    repo = ProductRepository(db)
    product = await repo.get_by_id(tenant_id=tenant_id, entity_id=product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found.",
        )
    return product
