import pytest
from decimal import Decimal
import uuid
from httpx import AsyncClient

from app.database.models import Tenant, Product
from app.core.router.router import MessageRouter
from app.core.router.intent import StructuredIntent
from app.core.ai_gateway import AIGateway
from tests.fake_ai import FakeAIProvider


@pytest.mark.asyncio
async def test_e2e_deterministic_price_query_without_ai(async_client: AsyncClient, test_session):
    """Proves that a clear price query is answered directly from DB truth without calling AI."""
    tenant = Tenant(name="E2E Tenant 1", slug="e2e-tenant-1", is_active=True)
    test_session.add(tenant)
    await test_session.commit()

    product = Product(
        tenant_id=tenant.id,
        name="Hoodie Black XL",
        sku="HOODIE-BLK-XL",
        price=Decimal("250000.00"),
        stock=15,
    )
    test_session.add(product)
    await test_session.commit()

    headers = {"X-Tenant-ID": str(tenant.id)}

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
                            "metadata": {"display_phone_number": "12345", "phone_number_id": "67890"},
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

    res = await async_client.post("/api/v1/integrations/whatsapp/webhook", json=webhook_payload, headers=headers)
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
