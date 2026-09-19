"""
GAP-006 Customer Identity Repair Verification Tests.

These tests verify deterministic customer identity resolution, phone vs external_id
conflict detection, duplicate external_id ambiguity handling, phoneless webhook sender
rejection, conversation active state alignment, cart ownership, and cross-tenant isolation.
"""

import uuid
import hmac
import hashlib
import json
import pytest
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.tenant import Tenant
from app.database.models.user import User
from app.database.models.customer import Customer
from app.database.models.conversation import Conversation
from app.database.models.product import Product
from app.database.models.order import Order
from app.database.models.integrations import Integration, IntegrationConnection, IntegrationCredential
from app.integrations.service import IntegrationService
from app.billing.plans import PlanService
from app.billing.subscription import SubscriptionService
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

    cust_a, _ = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone="+628111000111",
        name="Customer A",
        external_id="EXT-A",
    )
    await db_session.commit()

    cust_b, _ = await cust_repo.get_or_create(
        tenant_id=tenant_a.id,
        phone="+628111000222",
        name="Customer B",
        external_id="EXT-B",
    )
    await db_session.commit()

    assert cust_a.id != cust_b.id

    with pytest.raises(ValueError, match="IDENTITY_CONFLICT"):
        await cust_repo.get_or_create(
            tenant_id=tenant_a.id,
            phone="+628111000111",
            external_id="EXT-B",
        )


@pytest.mark.asyncio
async def test_duplicate_external_id_controlled_ambiguity_conflict(db_session: AsyncSession, tenant_a):
    """Points 5 & 6: get_by_external_id raises AMBIGUOUS_EXTERNAL_ID error when duplicate external_ids exist."""
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
    with pytest.raises(ValueError, match="AMBIGUOUS_EXTERNAL_ID"):
        await cust_repo.get_by_external_id(tenant_a.id, "EXT-SHARED-01")


@pytest.mark.asyncio
async def test_phoneless_webhook_sender_rejection_no_customer_created(async_client, db_session, tenant_a):
    """Points 1, 2, 7: Inbound WhatsApp message without sender_phone is rejected without creating permanent Customer."""
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    integration = Integration(
        integration_key="whatsapp_cloud_api",
        provider_key="whatsapp_cloud_api",
        display_name="WhatsApp Cloud API",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    phone_id_a = f"phone_anon_{uuid.uuid4().hex[:6]}"
    app_secret_a = "secret_anon_123"

    await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="whatsapp_cloud_api",
        credentials={"access_token": "token_a", "app_secret": app_secret_a, "phone_number_id": phone_id_a},
        external_account_id=phone_id_a,
        allow_internal=True,
    )

    # Payload with message missing "from" / sender_phone
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_id",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "123", "phone_number_id": phone_id_a},
                            "messages": [{"id": "wamid.anon_msg_1", "timestamp": "12345", "type": "text", "text": {"body": "Phoneless message"}}],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new(app_secret_a.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    resp = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["processed"][0]["status"] == "rejected_missing_sender_phone"

    # Verify NO Customer row was created for tenant_a
    cust_repo = CustomerRepository(db_session)
    customers = await cust_repo.list_all(tenant_a.id)
    assert len(customers) == 0


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

    conv = Conversation(
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        channel="whatsapp",
        status="HUMAN_ACTIVE",
    )
    db_session.add(conv)
    await db_session.commit()

    active_conv = await conv_repo.get_active_by_customer(
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        channel="whatsapp",
    )
    assert active_conv is not None
    assert active_conv.id == conv.id
    assert active_conv.status == "HUMAN_ACTIVE"

    conv_existing, created = await conv_repo.get_or_create_active(
        tenant_id=tenant_a.id,
        customer_id=customer.id,
        channel="whatsapp",
    )
    assert created is False
    assert conv_existing.id == conv.id


@pytest.mark.asyncio
async def test_cart_ownership_and_tenant_isolation(db_session: AsyncSession, tenant_a, tenant_b):
    """Decision D-006-06 / Point 9: Cart Order(status=CART) is deterministic and isolated by tenant and customer."""
    cust_repo = CustomerRepository(db_session)
    order_repo = OrderRepository(db_session)

    cust_a, _ = await cust_repo.get_or_create(tenant_a.id, phone="+62811000", name="Cart Cust A")
    cust_b, _ = await cust_repo.get_or_create(tenant_a.id, phone="+62822000", name="Cart Cust B")

    prod = Product(tenant_id=tenant_a.id, name="Cart Item", sku="CART-01", price=Decimal("100000.00"), stock=10)
    db_session.add(prod)
    await db_session.commit()

    # Create Cart order for Customer A
    cart_a = await order_repo.create_order_with_items(
        tenant_id=tenant_a.id,
        customer_id=cust_a.id,
        currency="IDR",
        items_data=[{"product": prod, "quantity": 1}],
        status="CART",
    )
    await db_session.commit()

    assert cart_a.status == "CART"
    assert cart_a.customer_id == cust_a.id

    # Tenant B lookup for Tenant A's Cart order returns None
    fetched_b = await order_repo.get_by_id(tenant_b.id, cart_a.id)
    assert fetched_b is None


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
