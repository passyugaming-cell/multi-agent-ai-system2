import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.order_state import validate_order_status_transition, InvalidOrderStateTransitionError, OrderStatus
from app.repositories.domain import OrderRepository, CustomerRepository
from app.database.models.tenant import Tenant


@pytest.mark.asyncio
async def test_01_valid_order_state_transitions():
    """Verifies valid ACT-111 Order state transition paths."""
    # CART -> ORDER_CREATED -> PAYMENT_PENDING -> PAID -> PROCESSING -> FULFILLED -> COMPLETED
    validate_order_status_transition("CART", "ORDER_CREATED")
    validate_order_status_transition("ORDER_CREATED", "PAYMENT_PENDING")
    validate_order_status_transition("PAYMENT_PENDING", "PAID")
    validate_order_status_transition("PAID", "PROCESSING")
    validate_order_status_transition("PROCESSING", "FULFILLED")
    validate_order_status_transition("FULFILLED", "COMPLETED")

    # FULFILLED -> RETURN_REQUESTED -> RETURNED
    validate_order_status_transition("FULFILLED", "RETURN_REQUESTED")
    validate_order_status_transition("RETURN_REQUESTED", "RETURNED")


@pytest.mark.asyncio
async def test_02_illegal_order_state_transitions_fail_closed():
    """Verifies that invalid state transitions raise InvalidOrderStateTransitionError."""
    # COMPLETED -> PAYMENT_PENDING
    with pytest.raises(InvalidOrderStateTransitionError):
        validate_order_status_transition("COMPLETED", "PAYMENT_PENDING")

    # CANCELLED -> PAID
    with pytest.raises(InvalidOrderStateTransitionError):
        validate_order_status_transition("CANCELLED", "PAID")

    # PAID -> CART
    with pytest.raises(InvalidOrderStateTransitionError):
        validate_order_status_transition("PAID", "CART")

    # FULFILLED -> PAYMENT_PENDING
    with pytest.raises(InvalidOrderStateTransitionError):
        validate_order_status_transition("FULFILLED", "PAYMENT_PENDING")

    # REFUNDED -> PAID
    with pytest.raises(InvalidOrderStateTransitionError):
        validate_order_status_transition("REFUNDED", "PAID")


@pytest.mark.asyncio
async def test_03_order_repository_transition_status_enforcement(db_session: AsyncSession, tenant_a: Tenant):
    """Verifies OrderRepository.transition_status enforces ACT-111 transitions with row locking."""
    cust_repo = CustomerRepository(db_session)
    customer, _ = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone="+628123456789",
        name="Test Customer",
    )

    from app.database.models.product import Product
    prod = Product(
        tenant_id=tenant_a.id,
        name="Test Item",
        price=50000.00,
        stock=10,
        is_active=True,
    )
    db_session.add(prod)
    await db_session.commit()

    order_repo = OrderRepository(db_session)
    order = await order_repo.create_order_with_items(
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        currency="IDR",
        items_data=[{"product": prod, "quantity": 1}],
    )
    await db_session.commit()

    # Initial order status is PENDING (maps to PENDING_CONFIRMATION / ORDER_CREATED)
    # Order status -> PAYMENT_PENDING -> PAID
    order.status = "ORDER_CREATED"
    await db_session.commit()

    updated = await order_repo.transition_status(tenant_a.id, order.id, "PAYMENT_PENDING")
    assert updated.status == "PAYMENT_PENDING"

    updated = await order_repo.transition_status(tenant_a.id, order.id, "PAID")
    assert updated.status == "PAID"

    # Attempt illegal transition: PAID -> CART -> must FAIL
    with pytest.raises(InvalidOrderStateTransitionError):
        await order_repo.transition_status(tenant_a.id, order.id, "CART")

    # Verify state remains unchanged as PAID
    await db_session.refresh(order)
    assert order.status == "PAID"
