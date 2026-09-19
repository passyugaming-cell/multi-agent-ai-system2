"""
GAP-006 Customer Identity Repair Verification Tests.

These tests verify deterministic customer identity resolution, phone vs external_id
conflict detection, anonymous sender isolation, conversation active state alignment,
and cross-tenant order ownership boundaries.
"""

import uuid
import pytest
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.database.models.user import User
from app.database.models.customer import Customer
from app.database.models.conversation import Conversation
from app.database.models.product import Product
from app.database.models.integrations import Integration, IntegrationConnection, IntegrationCredential
from app.repositories.domain import (
    CustomerRepository,
    ConversationRepository,
    OrderRepository,
)
from app.core.context import AuthenticatedActor, set_actor_context, reset_actor_context
from app.core.auth import ROLE_PERMISSIONS


@pytest.mark.asyncio
async def test_phone_vs_external_id_conflict_detection(db_session: AsyncSession, tenant_a):
    """D-006-04: Phone -> Customer A and External_ID -> Customer B raises explicit IDENTITY_CONFLICT error."""
    cust_repo = CustomerRepository(db_session)

    # 1. Create Customer A with phone_a and ext_id_a
    cust_a, _ = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone="+628111000111",
        name="Customer A",
        external_id="EXT-A",
    )
    await db_session.commit()

    # 2. Create Customer B with phone_b and ext_id_b
    cust_b, _ = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone="+628111000222",
        name="Customer B",
        external_id="EXT-B",
    )
    await db_session.commit()

    assert cust_a.id != cust_b.id

    # 3. Attempt get_or_create with phone_a (+628111000111) AND ext_id_b ("EXT-B")
    with pytest.raises(ValueError, match="IDENTITY_CONFLICT"):
        await cust_repo.get_or_create(
            tenant_id=tenant_a.id,
            phone="+628111000111",
            external_id="EXT-B",
        )


@pytest.mark.asyncio
async def test_anonymous_webhook_sender_isolation(async_client, db_session, tenant_a):
    """D-006-02: Anonymous/phone-less senders are assigned unique synthetic IDs and do NOT share hardcoded phone '628000000000'."""
    cust_repo = CustomerRepository(db_session)

    # 1. Create customer with phone = None, external_id = "anon_wa_msg_1"
    cust_1, created_1 = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone=None,
        name="Anonymous Customer 1",
        external_id="anon_wa_msg_1",
    )
    await db_session.commit()

    # 2. Create customer with phone = None, external_id = "anon_wa_msg_2"
    cust_2, created_2 = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone=None,
        name="Anonymous Customer 2",
        external_id="anon_wa_msg_2",
    )
    await db_session.commit()

    assert created_1 is True
    assert created_2 is True
    assert cust_1.id != cust_2.id
    assert cust_1.phone is None
    assert cust_2.phone is None
    assert cust_1.external_id == "anon_wa_msg_1"
    assert cust_2.external_id == "anon_wa_msg_2"


@pytest.mark.asyncio
async def test_conversation_active_status_alignment(db_session: AsyncSession, tenant_a):
    """Finding D / Conversation active status alignment: HUMAN_ACTIVE status is recognized as active."""
    cust_repo = CustomerRepository(db_session)
    conv_repo = ConversationRepository(db_session)

    customer, _ = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone="+6281234999",
        name="Active Conv Customer",
    )
    await db_session.commit()

    # Create conversation with status = "HUMAN_ACTIVE"
    conv = Conversation(
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        channel="whatsapp",
        status="HUMAN_ACTIVE",
    )
    db_session.add(conv)
    await db_session.commit()

    # get_active_by_customer must successfully find this active conversation
    active_conv = await conv_repo.get_active_by_customer(
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        channel="whatsapp",
    )
    assert active_conv is not None
    assert active_conv.id == conv.id
    assert active_conv.status == "HUMAN_ACTIVE"

    # get_or_create_active must return existing conv instead of attempting duplicate creation
    conv_existing, created = await conv_repo.get_or_create_active(
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        channel="whatsapp",
    )
    assert created is False
    assert conv_existing.id == conv.id


@pytest.mark.asyncio
async def test_get_by_external_id_non_crashing_first(db_session: AsyncSession, tenant_a):
    """Finding B / D-006-01: get_by_external_id safely returns scalar without throwing 500 MultipleResultsFound."""
    cust1 = Customer(
        tenant_id=tenant_a.id,
        name="Duplicate Ext 1",
        phone="+62811111",
        external_id="EXT-SHARED-01",
    )
    cust2 = Customer(
        tenant_id=tenant_a.id,
        name="Duplicate Ext 2",
        phone="+62822222",
        external_id="EXT-SHARED-01",
    )
    db_session.add_all([cust1, cust2])
    await db_session.commit()

    cust_repo = CustomerRepository(db_session)
    found = await cust_repo.get_by_external_id(tenant_a.id, "EXT-SHARED-01")
    assert found is not None
    assert found.id in (cust1.id, cust2.id)


@pytest.mark.asyncio
async def test_cross_customer_order_creation_rejection(async_client, db_session, tenant_a, tenant_b):
    """D-006-07: Creating an order for Tenant A using Customer B (from Tenant B) is rejected with HTTP 404."""
    user_a = User(tenant_id=tenant_a.id, email="owner_a_ord@test.com", password_hash="hash_a", is_active=True)
    db_session.add(user_a)

    cust_repo = CustomerRepository(db_session)
    cust_b, _ = await cust_repo.get_or_create(
        tenant_id=tenant_b.id,
        phone="+62819999999",
        name="Tenant B Customer",
    )
    await db_session.commit()

    token_a = set_actor_context(AuthenticatedActor(user_id=user_a.id, tenant_id=tenant_a.id, role="owner", permissions=set(ROLE_PERMISSIONS["owner"])))
    try:
        res = await async_client.post(
            "/api/v1/orders",
            json={
                "customer_id": str(cust_b.id),
                "currency": "IDR",
                "items": [],
            },
            headers={"X-Tenant-ID": str(tenant_a.id)},
        )
        assert res.status_code == 404
        assert "Customer not found" in str(res.json())
    finally:
        reset_actor_context(token_a)
