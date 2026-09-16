import pytest
import uuid
import hmac
import hashlib
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select

from app.database.models import Tenant, Customer, Conversation, Message
from app.database.models.integrations import Integration, IntegrationConnection, IntegrationCredential
from app.database.models.billing import Plan, Subscription, PlanFeature
from app.integrations.service import IntegrationService
from app.repositories.domain import MessageRepository


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
async def test_whatsapp_webhook_flow_and_idempotency(async_client: AsyncClient, test_session):
    tenant = Tenant(name="WA Tenant", slug=f"wa-tenant-{uuid.uuid4().hex[:6]}", is_active=True)
    test_session.add(tenant)
    await test_session.commit()

    app_secret = "secret_flow_123"
    phone_number_id = "67890"
    await _setup_active_whatsapp_integration(tenant, test_session, phone_number_id=phone_number_id, app_secret=app_secret)

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
                            "contacts": [
                                {
                                    "profile": {"name": "Budi Customer"},
                                    "wa_id": "628123456789",
                                }
                            ],
                            "messages": [
                                {
                                    "from": "628123456789",
                                    "id": f"wamid.flow_{uuid.uuid4().hex[:6]}",
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

    raw_bytes = json.dumps(webhook_payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"}

    # 1. First webhook delivery
    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)
    assert res.status_code == 200
    assert res.json()["status"] == "success"
    assert res.json()["processed"][0]["status"] == "processed"

    # 2. Duplicate webhook delivery (Idempotency check)
    res_dup = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)
    assert res_dup.status_code == 200
    assert res_dup.json()["status"] == "success"
    assert res_dup.json()["processed"][0]["status"] == "duplicate"


@pytest.mark.asyncio
async def test_human_handoff_stops_ai_response(async_client: AsyncClient, test_session):
    tenant = Tenant(name="Handoff Tenant", slug=f"handoff-tenant-{uuid.uuid4().hex[:6]}", is_active=True)
    test_session.add(tenant)
    await test_session.commit()

    app_secret = "secret_handoff_123"
    phone_number_id = "67891"
    await _setup_active_whatsapp_integration(tenant, test_session, phone_number_id=phone_number_id, app_secret=app_secret)

    customer = Customer(tenant_id=tenant.id, name="Jane", phone="62899999999")
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
                            "metadata": {"phone_number_id": phone_number_id},
                            "messages": [
                                {
                                    "from": "62899999999",
                                    "id": f"wamid.handoff_test_{uuid.uuid4().hex[:6]}",
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

    raw_bytes = json.dumps(webhook_payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"}

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)
    assert res.status_code == 200

    # Verify message was recorded and reply indicates human agent log
    msg_repo = MessageRepository(test_session)
    messages = await msg_repo.list_by_conversation(tenant.id, conv.id)
    assert len(messages) == 2  # 1 Inbound + 1 Outbound
    outbound = [m for m in messages if m.direction == "OUTBOUND"][0]
    assert "[SYSTEM] Message logged for human agent." in outbound.text
