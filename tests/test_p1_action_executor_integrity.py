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


@pytest.mark.asyncio
async def test_06_non_uuid_target_lookups_and_isolation(db_session: AsyncSession, tenant_a, tenant_b):
    """Verifies ActionExecutor safely resolves non-UUID targets (SKU/external ID/phone) and enforces tenant isolation."""
    # 1. Product with SKU target
    prod_a = Product(tenant_id=tenant_a.id, name="Tenant A SKU Item", sku="SKU_TENANT_A", price=100.00, stock=5, is_active=True)
    prod_b = Product(tenant_id=tenant_b.id, name="Tenant B SKU Item", sku="SKU_TENANT_B", price=200.00, stock=5, is_active=True)
    db_session.add_all([prod_a, prod_b])

    # 2. Customer with external_id target
    cust_repo = CustomerRepository(db_session)
    cust_a, _ = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone="+628777666555",
        name="Ext Cust A",
        external_id="EXT_CUST_A_123",
    )
    await db_session.commit()

    actor_a = AuthenticatedActor(
        user_id=uuid.uuid4(),
        tenant_id=tenant_a.id,
        role="owner",
        permissions={"product.write", "business.write", "product.read"},
        is_platform_owner=True,
    )
    token = set_actor_context(actor_a)
    try:
        # A. Valid SKU resolution for Tenant A (with valid approval for HIGH risk action)
        params_a = {"target": "SKU_TENANT_A", "price": "150.00"}
        hash_a = ActionBinding.compute_hash("change_product_price", "SKU_TENANT_A", tenant_a.id, params_a)
        appr_a = Approval(
            tenant_id=tenant_a.id,
            action_type="change_product_price",
            target="SKU_TENANT_A",
            risk_level="HIGH",
            requested_by="owner",
            reason="Price change",
            status="APPROVED",
            decided_by="platform_owner",
            meta_data={"params": params_a, "action_hash": hash_a, "decided_by_is_platform_owner": True},
        )
        db_session.add(appr_a)
        await db_session.commit()

        exec_params_a = dict(params_a)
        exec_params_a["_approval_id"] = str(appr_a.id)

        res1 = await ActionExecutor.execute(
            action_type="change_product_price",
            params=exec_params_a,
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
        assert res1.success is True
        assert res1.requires_approval is False
        await db_session.refresh(prod_a)
        assert prod_a.price == Decimal("150.00")

        # B. Non-existent SKU with approval -> FAIL (success=False)
        params_b = {"target": "SKU_NON_EXISTENT", "price": "150.00"}
        hash_b = ActionBinding.compute_hash("change_product_price", "SKU_NON_EXISTENT", tenant_a.id, params_b)
        appr_b = Approval(
            tenant_id=tenant_a.id,
            action_type="change_product_price",
            target="SKU_NON_EXISTENT",
            risk_level="HIGH",
            requested_by="owner",
            reason="Price change non existent",
            status="APPROVED",
            decided_by="platform_owner",
            meta_data={"params": params_b, "action_hash": hash_b, "decided_by_is_platform_owner": True},
        )
        db_session.add(appr_b)
        await db_session.commit()

        exec_params_b = dict(params_b)
        exec_params_b["_approval_id"] = str(appr_b.id)

        res2 = await ActionExecutor.execute(
            action_type="change_product_price",
            params=exec_params_b,
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
        assert res2.success is False
        assert "not found" in res2.error.lower()

        # C. Cross-tenant SKU lookup -> Tenant A requesting Tenant B's SKU must fail
        params_c = {"target": "SKU_TENANT_B", "price": "300.00"}
        hash_c = ActionBinding.compute_hash("change_product_price", "SKU_TENANT_B", tenant_a.id, params_c)
        appr_c = Approval(
            tenant_id=tenant_a.id,
            action_type="change_product_price",
            target="SKU_TENANT_B",
            risk_level="HIGH",
            requested_by="owner",
            reason="Cross tenant price change attempt",
            status="APPROVED",
            decided_by="platform_owner",
            meta_data={"params": params_c, "action_hash": hash_c, "decided_by_is_platform_owner": True},
        )
        db_session.add(appr_c)
        await db_session.commit()

        exec_params_c = dict(params_c)
        exec_params_c["_approval_id"] = str(appr_c.id)

        res3 = await ActionExecutor.execute(
            action_type="change_product_price",
            params=exec_params_c,
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
        assert res3.success is False
        assert "not found" in res3.error.lower()
        await db_session.refresh(prod_b)
        assert prod_b.price == Decimal("200.00")  # Tenant B price unchanged

        # D. Non-UUID External ID Customer resolution
        res4 = await ActionExecutor.execute(
            action_type="update_customer",
            params={"target": "EXT_CUST_A_123", "name": "Ext Cust A Updated"},
            context={},
            session=db_session,
            tenant_id=str(tenant_a.id),
        )
        assert res4.success is True
        await db_session.refresh(cust_a)
        assert cust_a.name == "Ext Cust A Updated"

    finally:
        reset_actor_context(token)
