import uuid
import hmac
import hashlib
import json
import pytest
from app.database.models.integrations import Integration
from app.integrations.service import IntegrationService
from app.billing.plans import PlanService
from app.billing.subscription import SubscriptionService


@pytest.mark.asyncio
async def test_whatsapp_tenant_mapping_ambiguity_rejection(async_client, db_session, tenant_a, tenant_b):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)
    await sub_srv.create_trial_subscription(tenant_b.id)

    # Seed whatsapp integration record
    integration = Integration(
        integration_key="whatsapp_cloud_api",
        provider_key="whatsapp_cloud_api",
        display_name="WhatsApp Cloud API",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    phone_id = "shared_phone_number_123"

    # Connect same phone_number_id for both Tenant A and Tenant B
    conn_a = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="whatsapp_cloud_api",
        credentials={"access_token": "token_a", "app_secret": "secret_a", "phone_number_id": phone_id},
        external_account_id=phone_id,
        allow_internal=True,
    )

    conn_b = await service.connect_integration(
        tenant_id=tenant_b.id,
        integration_key="whatsapp_cloud_api",
        credentials={"access_token": "token_b", "app_secret": "secret_b", "phone_number_id": phone_id},
        external_account_id=phone_id,
        allow_internal=True,
    )

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_id",
                "changes": [
                    {
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "123", "phone_number_id": phone_id},
                            "messages": [{"from": "62812345678", "id": "wamid.123", "timestamp": "12345", "type": "text", "text": {"body": "Hello"}}],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    # Ambiguous mapping should return 409 Conflict
    resp = await async_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert resp.status_code == 409
    assert "Ambiguous mapping" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_whatsapp_tenant_isolation_no_cross_tenant_bleed(async_client, db_session, tenant_a, tenant_b):
    plan_srv = PlanService(db_session)
    await plan_srv.seed_plans()

    sub_srv = SubscriptionService(db_session)
    await sub_srv.create_trial_subscription(tenant_a.id)

    # Seed whatsapp integration record
    integration = Integration(
        integration_key="whatsapp_cloud_api",
        provider_key="whatsapp_cloud_api",
        display_name="WhatsApp Cloud API",
        is_enabled=True,
    )
    db_session.add(integration)
    await db_session.commit()

    service = IntegrationService(db_session)
    phone_id_a = "phone_tenant_a_123"

    conn_a = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="whatsapp_cloud_api",
        credentials={"access_token": "token_a", "app_secret": "secret_a", "phone_number_id": phone_id_a},
        external_account_id=phone_id_a,
        allow_internal=True,
    )

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
                            "messages": [{"from": "62812345678", "id": "wamid.unique_msg_1", "timestamp": "12345", "type": "text", "text": {"body": "Hello Tenant A"}}],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new("secret_a".encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    resp = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"},
    )
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["tenant_id"] == str(tenant_a.id)
    assert res_data["tenant_id"] != str(tenant_b.id)
