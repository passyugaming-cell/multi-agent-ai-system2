from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.repositories.domain import OrderRepository, ProductRepository, CustomerRepository
from app.schemas.domain import OrderCreate, OrderResponse

router = APIRouter(prefix="/orders", tags=["Orders"])


def _get_tenant_id_or_400() -> UUID:
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID context missing or invalid.",
        )
    return tenant_id


@router.get("", response_model=list[OrderResponse])
async def list_orders(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = _get_tenant_id_or_400()
    repo = OrderRepository(db)
    return await repo.list_all(tenant_id=tenant_id, skip=skip, limit=limit)


@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = _get_tenant_id_or_400()
    customer_repo = CustomerRepository(db)
    product_repo = ProductRepository(db)
    order_repo = OrderRepository(db)

    customer = await customer_repo.get_by_id(tenant_id, payload.customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found for tenant.",
        )

    items_data = []
    for item in payload.items:
        if not item.product_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="product_id is required for each order item.",
            )
        product = await product_repo.get_by_id(tenant_id, item.product_id)
        if not product:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Product {item.product_id} not found for tenant.",
            )
        items_data.append({"product": product, "quantity": item.quantity})

    order = await order_repo.create_order_with_items(
        tenant_id=tenant_id,
        customer_id=payload.customer_id,
        currency=payload.currency,
        items_data=items_data,
        metadata=payload.metadata,
    )
    await db.commit()

    full_order = await order_repo.get_by_id_with_items(tenant_id, order.id)
    return full_order
