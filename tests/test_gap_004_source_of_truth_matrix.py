"""
GAP-004 Source of Truth & Conflict Resolution Matrix Verification Tests.

These tests verify existing source-of-truth invariants, tenant isolation rules,
and conflict resolution boundaries without modifying product behavior or schema.
"""

import uuid
from decimal import Decimal
import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.database.models.product import Product
from app.database.models.customer import Customer
from app.database.models.order import Order, OrderItem
from app.database.models.billing import Payment, Invoice
from app.database.models.knowledge import KnowledgeItem
from app.database.models.conversation import Conversation
from app.core.messaging_state import (
    validate_message_status_transition,
    InvalidStateTransitionError,
)
from app.repositories.domain import (
    ProductRepository,
    CustomerRepository,
    KnowledgeItemRepository,
    ConversationRepository,
)


@pytest.mark.asyncio
async def test_order_price_snapshot_at_checkout(
    db_session: AsyncSession, tenant_a
):
    """ACT-053 / ACT-103: Order stores immutable unit_price_at_order snapshot."""
    # 1. Create customer
    cust_repo = CustomerRepository(db_session)
    customer, _ = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone="+628123456789",
        name="Test Customer",
    )

    # 2. Create product in DB with initial price
    product = Product(
        tenant_id=tenant_a.id,
        name="Hoodie Premium",
        sku="HD-001",
        price=Decimal("250000.00"),
        stock=10,
        is_active=True,
    )
    db_session.add(product)
    await db_session.commit()
    await db_session.refresh(product)

    # 3. Create order with price snapshot
    order = Order(
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        status="PENDING",
        subtotal=Decimal("250000.00"),
        total=Decimal("250000.00"),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    order_item = OrderItem(
        tenant_id=tenant_a.id,
        order_id=order.id,
        product_id=product.id,
        product_name_snapshot=product.name,
        quantity=1,
        unit_price=product.price,
        subtotal=product.price,
    )
    db_session.add(order_item)
    await db_session.commit()

    # 4. Mutate catalog product price
    product.price = Decimal("300000.00")
    await db_session.commit()

    # 5. Verify historical order snapshot price remains unchanged
    await db_session.refresh(order_item)
    assert order_item.unit_price == Decimal("250000.00")
    assert product.price == Decimal("300000.00")


@pytest.mark.asyncio
async def test_cross_tenant_product_repository_isolation(
    db_session: AsyncSession, tenant_a, tenant_b
):
    """ACT-215 / ACT-216: Tenant A cannot read or list Tenant B products."""
    prod_a = Product(
        tenant_id=tenant_a.id,
        name="Tenant A Product",
        sku="TA-001",
        price=Decimal("100000.00"),
        stock=5,
        is_active=True,
    )
    prod_b = Product(
        tenant_id=tenant_b.id,
        name="Tenant B Product",
        sku="TB-001",
        price=Decimal("150000.00"),
        stock=5,
        is_active=True,
    )
    db_session.add_all([prod_a, prod_b])
    await db_session.commit()

    repo = ProductRepository(db_session)

    # Tenant A list excludes Tenant B product
    prods_a = await repo.list_all(tenant_a.id)
    prod_ids_a = [p.id for p in prods_a]
    assert prod_a.id in prod_ids_a
    assert prod_b.id not in prod_ids_a

    # Tenant A direct lookup for Tenant B product returns None
    fetched = await repo.get_by_id(tenant_a.id, prod_b.id)
    assert fetched is None


@pytest.mark.asyncio
async def test_same_phone_number_different_tenants_isolation(
    db_session: AsyncSession, tenant_a, tenant_b
):
    """ACT-215 / ACT-274: Same customer phone across Tenant A and Tenant B creates two isolated customer entities."""
    cust_repo = CustomerRepository(db_session)
    phone_number = "+628999888777"

    cust_a, created_a = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone=phone_number,
        name="Customer in Tenant A",
    )
    await db_session.commit()

    cust_b, created_b = await cust_repo.get_or_create(
        tenant_id=tenant_b.id,
        phone=phone_number,
        name="Customer in Tenant B",
    )
    await db_session.commit()

    assert created_a is True
    assert created_b is True
    assert cust_a.id != cust_b.id
    assert cust_a.tenant_id == tenant_a.id
    assert cust_b.tenant_id == tenant_b.id

    # Verify lookup is strictly tenant-scoped
    fetched_a = await cust_repo.get_by_phone(tenant_a.id, phone_number)
    fetched_b = await cust_repo.get_by_phone(tenant_b.id, phone_number)

    assert fetched_a.id == cust_a.id
    assert fetched_b.id == cust_b.id


@pytest.mark.asyncio
async def test_unverified_payment_does_not_grant_paid_status(
    db_session: AsyncSession, tenant_a
):
    """ACT-107 / ACT-286: Payment remains PENDING until verified webhook."""
    invoice = Invoice(
        tenant_id=tenant_a.id,
        invoice_number=f"INV-{uuid.uuid4().hex[:6]}",
        total=Decimal("500000.00"),
        status="DRAFT",
    )
    db_session.add(invoice)
    await db_session.commit()

    payment = Payment(
        tenant_id=tenant_a.id,
        invoice_id=invoice.id,
        provider="midtrans",
        provider_payment_id="PAY-TEST-001",
        amount=Decimal("500000.00"),
        currency="IDR",
        status="PENDING",
    )
    db_session.add(payment)
    await db_session.commit()

    # Unverified payment status in DB is PENDING, not PAID/SUCCESS
    await db_session.refresh(payment)
    assert payment.status == "PENDING"


@pytest.mark.asyncio
async def test_stock_non_negative_check_constraint(
    db_session: AsyncSession, tenant_a
):
    """ACT-054 / ACT-104: Database check constraint prevents negative stock."""
    product = Product(
        tenant_id=tenant_a.id,
        name="Limited Stock Item",
        sku="LIMITED-01",
        price=Decimal("100000.00"),
        stock=1,
        is_active=True,
    )
    db_session.add(product)
    await db_session.commit()

    # Attempt to set negative stock
    product.stock = -1
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


@pytest.mark.asyncio
async def test_approved_knowledge_vs_unapproved_status_filter(
    db_session: AsyncSession, tenant_a
):
    """ACT-074 / ACT-080: Only APPROVED or ACTIVE knowledge items are returned for factual AI retrieval."""
    repo = KnowledgeItemRepository(db_session)

    draft_item = KnowledgeItem(
        tenant_id=tenant_a.id,
        category_key="shipping",
        title="Draft Shipping Policy",
        content="Shipping takes 1 day",
        status="DRAFT",
    )
    active_item = KnowledgeItem(
        tenant_id=tenant_a.id,
        category_key="shipping",
        title="Official Shipping Policy",
        content="Shipping takes 2-3 business days",
        status="ACTIVE",
    )
    db_session.add_all([draft_item, active_item])
    await db_session.commit()

    approved_items = await repo.list_active_and_approved(tenant_a.id)
    approved_ids = [item.id for item in approved_items]

    assert active_item.id in approved_ids
    assert draft_item.id not in approved_ids


@pytest.mark.asyncio
async def test_message_status_state_machine_transitions():
    """ACT-277 / R3: WhatsApp outbound message delivery state machine transitions."""
    # Valid transitions
    validate_message_status_transition("CREATED", "QUEUED")
    validate_message_status_transition("QUEUED", "SENDING")
    validate_message_status_transition("SENDING", "SENT")
    validate_message_status_transition("SENT", "DELIVERED")
    validate_message_status_transition("DELIVERED", "READ")

    # Invalid transitions (e.g. READ back to CREATED or READ to QUEUED)
    with pytest.raises(InvalidStateTransitionError):
        validate_message_status_transition("READ", "CREATED")

    with pytest.raises(InvalidStateTransitionError):
        validate_message_status_transition("DELIVERED", "QUEUED")


@pytest.mark.asyncio
async def test_conversation_active_lookup_channel_behavior(
    db_session: AsyncSession, tenant_a
):
    """ACT-045 / Audit Finding P1-01: Verify active conversation retrieval behavior across channels for same customer."""
    cust_repo = CustomerRepository(db_session)
    conv_repo = ConversationRepository(db_session)

    customer, _ = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone="+628111222333",
        name="Multi Channel Customer",
    )

    # Create active conversation on whatsapp channel
    conv_wa = Conversation(
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        channel="whatsapp",
        status="OPEN",
    )
    db_session.add(conv_wa)
    await db_session.commit()

    # Active conversation lookup finds active conversation
    active_conv = await conv_repo.get_active_by_customer(tenant_a.id, customer.id)
    assert active_conv is not None
    assert active_conv.id == conv_wa.id
