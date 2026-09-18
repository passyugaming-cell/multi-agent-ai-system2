import uuid
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.workflows.actions import ActionExecutor
from app.repositories.domain import CustomerRepository, OrderRepository, ProductRepository
from app.database.models.product import Product
from app.database.models.workflow import Approval
from app.billing.invoices import InvoiceService
from app.billing.payments import PaymentService
from app.billing.refunds import RefundService
from app.core.authority.schemas import ActionBinding
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context


@pytest.mark.asyncio
async def test_01_update_customer_real_db_mutation(db_session: AsyncSession, tenant_a):
    """Verifies update_customer action performs actual database mutation."""
    cust_repo = CustomerRepository(db_session)
    customer, _ = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone="+628111222333",
        name="Original Name",
    )
    await db_session.commit()

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"business.write"},
    )
    token = set_actor_context(actor)
    try:
        res = await ActionExecutor.execute(
            action_type="update_customer",
            params={"customer_id": str(customer.id), "name": "Updated Name"},
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
    finally:
        reset_actor_context(token)

    assert res.success is True
    assert res.output["name"] == "Updated Name"

    await db_session.refresh(customer)
    assert customer.name == "Updated Name"


@pytest.mark.asyncio
async def test_02_update_order_state_machine_enforcement(db_session: AsyncSession, tenant_a):
    """Verifies update_order enforces ACT-111 state machine transitions on real Order record."""
    cust_repo = CustomerRepository(db_session)
    customer, _ = await cust_repo.get_or_create(tenant_id=tenant_a.id, phone="+628111222333", name="Customer 1")

    prod = Product(tenant_id=tenant_a.id, name="Item 1", price=100000.00, stock=5, is_active=True)
    db_session.add(prod)
    await db_session.commit()

    order_repo = OrderRepository(db_session)
    order = await order_repo.create_order_with_items(
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        currency="IDR",
        items_data=[{"product": prod, "quantity": 1}],
    )
    order.status = "ORDER_CREATED"
    await db_session.commit()

    actor = AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="owner", permissions={"business.write"})
    token = set_actor_context(actor)
    try:
        # Valid transition: ORDER_CREATED -> PAYMENT_PENDING
        res1 = await ActionExecutor.execute(
            action_type="update_order",
            params={"order_id": str(order.id), "status": "PAYMENT_PENDING"},
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
        assert res1.success is True
        assert res1.output["status"] == "PAYMENT_PENDING"

        # Illegal transition: PAYMENT_PENDING -> CART -> must FAIL
        res2 = await ActionExecutor.execute(
            action_type="update_order",
            params={"order_id": str(order.id), "status": "CART"},
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
        assert res2.success is False
        assert "state transition rejected" in res2.error.lower()
    finally:
        reset_actor_context(token)

    await db_session.refresh(order)
    assert order.status == "PAYMENT_PENDING"


@pytest.mark.asyncio
async def test_03_change_product_price_real_db_mutation(db_session: AsyncSession, tenant_a):
    """Verifies change_product_price updates authoritative product price in database with valid approval."""
    prod = Product(tenant_id=tenant_a.id, name="P1", price=50000.00, stock=10, is_active=True)
    db_session.add(prod)
    await db_session.commit()

    params = {"product_id": str(prod.id), "price": "75000.00"}
    action_hash = ActionBinding.compute_hash(
        action_type="change_product_price",
        target="change_product_price",
        tenant_id=tenant_a.id,
        params=params,
    )
    approval = Approval(
        tenant_id=tenant_a.id,
        action_type="change_product_price",
        target="change_product_price",
        risk_level="HIGH",
        requested_by="owner",
        reason="Price adjustment",
        status="APPROVED",
        decided_by="platform_owner",
        meta_data={"params": params, "action_hash": action_hash, "decided_by_is_platform_owner": True},
    )
    db_session.add(approval)
    await db_session.commit()

    exec_params = dict(params)
    exec_params["_approval_id"] = str(approval.id)

    actor = AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="owner", permissions={"product.write"}, is_platform_owner=True)
    token = set_actor_context(actor)
    try:
        res = await ActionExecutor.execute(
            action_type="change_product_price",
            params=exec_params,
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
    finally:
        reset_actor_context(token)

    assert res.success is True
    assert res.output["new_price"] == "75000.00"

    await db_session.refresh(prod)
    assert prod.price == Decimal("75000.00")


@pytest.mark.asyncio
async def test_04_unapproved_issue_refund_rejected(db_session: AsyncSession, tenant_a):
    """CRITICAL action issue_refund without valid database approval requires approval (requires_approval=True)."""
    actor = AuthenticatedActor(user_id=uuid.uuid4(), tenant_id=tenant_a.id, role="owner", permissions={"APPROVE_REFUND"})
    token = set_actor_context(actor)
    try:
        res = await ActionExecutor.execute(
            action_type="issue_refund",
            params={"payment_id": str(uuid.uuid4()), "amount": "50000.00"},
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
    finally:
        reset_actor_context(token)

    assert res.requires_approval is True


@pytest.mark.asyncio
async def test_05_approved_issue_refund_executes_real_refund(db_session: AsyncSession, tenant_a):
    """Approved issue_refund executes real refund via RefundService and updates payment state."""
    inv_service = InvoiceService(db_session)
    invoice = await inv_service.create_invoice(
        tenant_id=tenant_a.id,
        items_data=[{"description": "Refund Item", "unit_price": Decimal("100000.00"), "quantity": 1}],
    )

    pay_service = PaymentService(db_session)
    payment = await pay_service.create_payment_intent(
        tenant_id=tenant_a.id,
        invoice_id=invoice.id,
        amount=invoice.total,
    )
    await pay_service.confirm_payment_success(tenant_a.id, payment.id, "tx_settled_123")
    await db_session.commit()

    refund_service = RefundService(db_session)
    approval = await refund_service.request_refund(
        tenant_id=tenant_a.id,
        payment_id=payment.id,
        amount=Decimal("100000.00"),
        reason="Defective item",
        requested_by="customer_service",
    )

    params = {"payment_id": str(payment.id), "amount": "100000.00", "reason": "Refund request for payment " + str(payment.id) + ": Defective item"}
    action_hash = ActionBinding.compute_hash(
        action_type="issue_refund",
        target="issue_refund",
        tenant_id=tenant_a.id,
        params=params,
    )

    approval.status = "APPROVED"
    approval.decided_by = "platform_owner"
    approval.meta_data = {
        "payment_id": str(payment.id),
        "amount": "100000.00",
        "reason": "Defective item",
        "params": params,
        "action_hash": action_hash,
        "decided_by_is_platform_owner": True,
    }
    await db_session.commit()

    exec_params = dict(params)
    exec_params["_approval_id"] = str(approval.id)

    actor = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"APPROVE_REFUND"},
        is_platform_owner=True,
    )
    token = set_actor_context(actor)
    try:
        res = await ActionExecutor.execute(
            action_type="issue_refund",
            params=exec_params,
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
    finally:
        reset_actor_context(token)

    assert res.success is True, f"Error: {res.error}"
    assert res.output["status"] == "REFUNDED"

    await db_session.refresh(payment)
    assert payment.status == "REFUNDED"
    assert payment.refunded_amount == Decimal("100000.00")
