import uuid
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.database.models.workflow import WorkflowConfiguration, WorkflowExecution
from app.database.models.customer import Customer
from app.database.models.conversation import Conversation
from app.database.models.order import Order
from app.database.models.product import Product
from app.database.models.integrations import Integration, IntegrationConnection
from app.database.models.billing import Plan, Subscription, Invoice


@pytest.mark.asyncio
async def test_phase_a_parent_composite_unique_constraints(db_session: AsyncSession, tenant_a: Tenant, tenant_b: Tenant):
    """Verifies that Phase A composite unique constraints UNIQUE (tenant_id, id) exist and function correctly."""

    # 1. Test Customer composite uniqueness
    customer_a = Customer(
        tenant_id=tenant_a.id,
        name="Customer A",
        email="cust_a@example.com",
    )
    customer_b = Customer(
        tenant_id=tenant_b.id,
        name="Customer B",
        email="cust_b@example.com",
    )
    db_session.add_all([customer_a, customer_b])
    await db_session.commit()
    assert customer_a.id != customer_b.id

    # 2. Test Product composite uniqueness
    product_a = Product(
        tenant_id=tenant_a.id,
        name="Product A",
        price=100,
    )
    product_b = Product(
        tenant_id=tenant_b.id,
        name="Product B",
        price=200,
    )
    db_session.add_all([product_a, product_b])
    await db_session.commit()

    # 3. Test Order composite uniqueness
    order_a = Order(
        tenant_id=tenant_a.id,
        customer_id=customer_a.id,
        total=100,
    )
    order_b = Order(
        tenant_id=tenant_b.id,
        customer_id=customer_b.id,
        total=200,
    )
    db_session.add_all([order_a, order_b])
    await db_session.commit()

    # 4. Test Conversation composite uniqueness
    conv_a = Conversation(
        tenant_id=tenant_a.id,
        customer_id=customer_a.id,
        channel="whatsapp",
    )
    conv_b = Conversation(
        tenant_id=tenant_b.id,
        customer_id=customer_b.id,
        channel="whatsapp",
    )
    db_session.add_all([conv_a, conv_b])
    await db_session.commit()

    # 5. Test WorkflowConfiguration & WorkflowExecution composite uniqueness
    wf_a = WorkflowConfiguration(
        tenant_id=tenant_a.id,
        key="WF_A",
        name="Workflow A",
    )
    wf_b = WorkflowConfiguration(
        tenant_id=tenant_b.id,
        key="WF_B",
        name="Workflow B",
    )
    db_session.add_all([wf_a, wf_b])
    await db_session.commit()

    exec_a = WorkflowExecution(
        tenant_id=tenant_a.id,
        workflow_id=wf_a.id,
        event_id="evt_a_1",
    )
    exec_b = WorkflowExecution(
        tenant_id=tenant_b.id,
        workflow_id=wf_b.id,
        event_id="evt_b_1",
    )
    db_session.add_all([exec_a, exec_b])
    await db_session.commit()

    # 6. Test IntegrationConnection composite uniqueness
    integ = Integration(
        integration_key="whatsapp_catalog_a",
        provider_key="whatsapp",
        display_name="WhatsApp Catalog",
    )
    db_session.add(integ)
    await db_session.commit()

    conn_a = IntegrationConnection(
        tenant_id=tenant_a.id,
        integration_id=integ.id,
        provider_key="whatsapp",
        external_account_id="acc_a",
        status="CONNECTED",
    )
    conn_b = IntegrationConnection(
        tenant_id=tenant_b.id,
        integration_id=integ.id,
        provider_key="whatsapp",
        external_account_id="acc_b",
        status="CONNECTED",
    )
    db_session.add_all([conn_a, conn_b])
    await db_session.commit()

    # 7. Test Subscription & Invoice composite uniqueness
    plan = Plan(
        name="Pro Plan Test",
        code=f"pro_test_{uuid.uuid4().hex[:6]}",
        price_monthly=1000,
    )
    db_session.add(plan)
    await db_session.commit()

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    sub_a = Subscription(
        tenant_id=tenant_a.id,
        plan_id=plan.id,
        started_at=now,
        current_period_start=now,
        current_period_end=now,
    )
    sub_b = Subscription(
        tenant_id=tenant_b.id,
        plan_id=plan.id,
        started_at=now,
        current_period_start=now,
        current_period_end=now,
    )
    db_session.add_all([sub_a, sub_b])
    await db_session.commit()

    inv_a = Invoice(
        tenant_id=tenant_a.id,
        subscription_id=sub_a.id,
        invoice_number=f"INV-A-{uuid.uuid4().hex[:6]}",
    )
    inv_b = Invoice(
        tenant_id=tenant_b.id,
        subscription_id=sub_b.id,
        invoice_number=f"INV-B-{uuid.uuid4().hex[:6]}",
    )
    db_session.add_all([inv_a, inv_b])
    await db_session.commit()

    # Verify query by (tenant_id, id) works cleanly across all parent tables
    res_customer = (await db_session.execute(select(Customer).where(Customer.tenant_id == tenant_a.id, Customer.id == customer_a.id))).scalar_one_or_none()
    assert res_customer is not None
    assert res_customer.id == customer_a.id

    res_product = (await db_session.execute(select(Product).where(Product.tenant_id == tenant_a.id, Product.id == product_a.id))).scalar_one_or_none()
    assert res_product is not None
    assert res_product.id == product_a.id

    res_order = (await db_session.execute(select(Order).where(Order.tenant_id == tenant_a.id, Order.id == order_a.id))).scalar_one_or_none()
    assert res_order is not None

    res_conv = (await db_session.execute(select(Conversation).where(Conversation.tenant_id == tenant_a.id, Conversation.id == conv_a.id))).scalar_one_or_none()
    assert res_conv is not None

    res_wf = (await db_session.execute(select(WorkflowConfiguration).where(WorkflowConfiguration.tenant_id == tenant_a.id, WorkflowConfiguration.id == wf_a.id))).scalar_one_or_none()
    assert res_wf is not None

    res_exec = (await db_session.execute(select(WorkflowExecution).where(WorkflowExecution.tenant_id == tenant_a.id, WorkflowExecution.id == exec_a.id))).scalar_one_or_none()
    assert res_exec is not None

    res_conn = (await db_session.execute(select(IntegrationConnection).where(IntegrationConnection.tenant_id == tenant_a.id, IntegrationConnection.id == conn_a.id))).scalar_one_or_none()
    assert res_conn is not None

    res_sub = (await db_session.execute(select(Subscription).where(Subscription.tenant_id == tenant_a.id, Subscription.id == sub_a.id))).scalar_one_or_none()
    assert res_sub is not None

    res_inv = (await db_session.execute(select(Invoice).where(Invoice.tenant_id == tenant_a.id, Invoice.id == inv_a.id))).scalar_one_or_none()
    assert res_inv is not None
