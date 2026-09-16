import pytest
from decimal import Decimal
import uuid
import hmac
import hashlib
import json
from datetime import datetime, timezone, timedelta
from httpx import AsyncClient
from sqlalchemy import select

from app.database.models import Tenant, Product, Subscription, Plan, PlanFeature
from app.database.models.integrations import Integration, IntegrationConnection, IntegrationCredential
from app.integrations.service import IntegrationService
from app.core.router.router import MessageRouter
from app.core.router.intent import StructuredIntent
from app.core.ai_gateway import AIGateway
from tests.fake_ai import FakeAIProvider


async def _setup_active_whatsapp_integration(tenant, db_session, phone_number_id="67890", app_secret="test_secret_123"):
    stmt = select(Integration).where(Integration.integration_key == "whatsapp_cloud_api")
    integration = (await db_session.execute(stmt)).scalars().first()
    if not integration:
        integration = Integration(
            display_name="WhatsApp Cloud API",
            integration_key="whatsapp_cloud_api",
            provider_key="whatsapp_cloud_api",
            category="channel",
            status="AVAILABLE",
            is_enabled=True,
            configuration={"api_version": "v18.0"},
        )
        db_session.add(integration)
        await db_session.commit()

    plan = Plan(
        name="Pro Plan",
        code=f"pro_{uuid.uuid4().hex[:6]}",
        price_monthly=Decimal("100.00"),
        price_yearly=Decimal("1000.00"),
        currency="IDR",
        is_active=True,
    )
    db_session.add(plan)
    await db_session.commit()

    pf = PlanFeature(
        plan_id=plan.id,
        feature_key="whatsapp_cloud_api",
        is_enabled=True,
    )
    db_session.add(pf)
    await db_session.commit()

    now = datetime.now(timezone.utc)
    sub = Subscription(
        tenant_id=tenant.id,
        plan_id=plan.id,
        status="ACTIVE",
        billing_cycle="MONTHLY",
        started_at=now,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )
    db_session.add(sub)
    await db_session.commit()

    conn = IntegrationConnection(
        tenant_id=tenant.id,
        integration_id=integration.id,
        status="ACTIVE",
        external_account_id=phone_number_id,
        meta_data={"phone_number_id": phone_number_id},
    )
    db_session.add(conn)
    await db_session.commit()

    service = IntegrationService(db_session)
    creds_dict = {
        "phone_number_id": phone_number_id,
        "access_token": "test_access_token",
        "app_secret": app_secret,
        "verify_token": "test_verify_token",
    }
    enc_secret = service.vault.encrypt_credentials(creds_dict)

    cred = IntegrationCredential(
        tenant_id=tenant.id,
        connection_id=conn.id,
        credential_type="bearer_token",
        encrypted_secret=enc_secret,
    )
    db_session.add(cred)
    await db_session.commit()
    return conn


@pytest.mark.asyncio
async def test_e2e_deterministic_price_query_without_ai(async_client: AsyncClient, test_session):
    """Proves that a clear price query is answered directly from DB truth without calling AI."""
    tenant = Tenant(name="E2E Tenant 1", slug="e2e-tenant-1", is_active=True)
    test_session.add(tenant)
    await test_session.commit()

    app_secret = "secret_e2e_123"
    phone_number_id = "67890"
    await _setup_active_whatsapp_integration(tenant, test_session, phone_number_id=phone_number_id, app_secret=app_secret)

    product = Product(
        tenant_id=tenant.id,
        name="Hoodie Black XL",
        sku="HOODIE-BLK-XL",
        price=Decimal("250000.00"),
        stock=15,
    )
    test_session.add(product)
    await test_session.commit()

    webhook_payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "12345", "phone_number_id": phone_number_id},
                            "contacts": [{"profile": {"name": "Test Customer"}, "wa_id": "08111111111"}],
                            "messages": [
                                {
                                    "from": "08111111111",
                                    "id": "wamid.e2e_det_price_1",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "Berapa harga Hoodie Black XL?"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    raw_bytes = json.dumps(webhook_payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"}

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)
    assert res.status_code == 200
    processed = res.json()["processed"][0]
    assert processed["status"] == "processed"
    assert processed["was_ai_called"] is False  # ZERO AI CALLS MADE!


@pytest.mark.asyncio
async def test_e2e_ambiguous_query_uses_ai_intent_and_db_truth(test_session):
    """Proves that an ambiguous query uses AI for intent classification, but DB supplies exact facts."""
    tenant = Tenant(name="E2E Tenant 2", slug="e2e-tenant-2", is_active=True)
    test_session.add(tenant)
    await test_session.commit()

    product = Product(
        tenant_id=tenant.id,
        name="Sepatu Lari Red",
        sku="SHOE-RED-42",
        price=Decimal("450000.00"),
        stock=8,
    )
    test_session.add(product)
    await test_session.commit()

    # Fake AI Provider returns structured intent for "Sepatu Lari Red"
    fake_intent = StructuredIntent(
        intent="check_stock",
        confidence=0.98,
        action="GET_PRODUCT_STOCK",
        product_name_query="Sepatu Lari Red",
    )
    fake_ai = FakeAIProvider(default_structured_output=fake_intent)
    gateway = AIGateway(provider=fake_ai)

    router = MessageRouter(ai_gateway=gateway)

    from app.database.models import Conversation, Message, Customer
    cust = Customer(tenant_id=tenant.id, name="Test", phone="0822222")
    test_session.add(cust)
    await test_session.commit()

    conv = Conversation(
        tenant_id=tenant.id,
        customer_id=cust.id,
        channel="whatsapp",
        status="OPEN",
        human_handoff=False,
        ai_enabled=True,
    )
    test_session.add(conv)
    await test_session.commit()

    msg_ambiguous = Message(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="INBOUND",
        text="Mohon info terkait unit pangkas catalog",  # No deterministic price/stock keyword match
    )

    result = await router.route_message(tenant.id, conv, msg_ambiguous, test_session)

    assert result.was_ai_called is True
    assert "Stok Sepatu Lari Red tersedia 8 unit." in result.response_text
    assert result.matched_product.id == product.id
