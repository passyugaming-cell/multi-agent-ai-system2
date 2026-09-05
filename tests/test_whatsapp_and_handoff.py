import pytest
import uuid
from httpx import AsyncClient
from app.database.models import Tenant, Product, Customer, Conversation, Message
from app.repositories.domain import MessageRepository, ConversationRepository


@pytest.mark.asyncio
async def test_whatsapp_webhook_flow_and_idempotency(async_client: AsyncClient, test_session):
    tenant = Tenant(name="WA Tenant", slug="wa-tenant", is_active=True)
    test_session.add(tenant)
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
                            "contacts": [
                                {
                                    "profile": {"name": "Budi Customer"},
                                    "wa_id": "628123456789",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "628123456789",
                                    "id": "wamid.HBgLMTYyODEyMzQ1Njc4OQ==",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "Halo, permisi"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    # 1. First webhook delivery
    res = await async_client.post("/api/v1/integrations/whatsapp/webhook", json=webhook_payload, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["processed"][0]["status"] == "processed"

    # 2. Duplicate webhook delivery (Idempotency check)
    res_dup = await async_client.post("/api/v1/integrations/whatsapp/webhook", json=webhook_payload, headers=headers)
    assert res_dup.status_code == 200
    assert res_dup.json()["status"] == "success"
    assert res_dup.json()["processed"][0]["status"] == "duplicate"


@pytest.mark.asyncio
async def test_human_handoff_stops_ai_response(async_client: AsyncClient, test_session):
    tenant = Tenant(name="Handoff Tenant", slug="handoff-tenant", is_active=True)
    test_session.add(tenant)
    await test_session.commit()

    customer = Customer(tenant_id=tenant.id, name="Jane", phone="0899999999")
    test_session.add(customer)
    await test_session.commit()

    # Conversation with human_handoff = True
    conv = Conversation(
        tenant_id=tenant.id,
        customer_id=customer.id,
        channel="whatsapp",
        status="OPEN",
        human_handoff=True,
        ai_enabled=False,
    )
    test_session.add(conv)
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
                            "messages": [
                                {
                                    "from": "0899999999",
                                    "id": "wamid.handoff_test_123",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "Bisa minta bantuan manusia?"},
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

    # Verify message was recorded and reply indicates human agent log
    msg_repo = MessageRepository(test_session)
    messages = await msg_repo.list_by_conversation(tenant.id, conv.id)
    assert len(messages) == 2  # 1 Inbound + 1 Outbound
    outbound = [m for m in messages if m.direction == "OUTBOUND"][0]
    assert "[SYSTEM] Message logged for human agent." in outbound.text
