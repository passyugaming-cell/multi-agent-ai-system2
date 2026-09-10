import uuid
import hmac
import hashlib
import json
import pytest
from app.database.models.integrations import Integration, IntegrationConnection
from app.integrations.service import IntegrationService
from app.integrations.exceptions import PermanentIntegrationError
from app.billing.plans import PlanService
from app.billing.subscription import SubscriptionService


@pytest.mark.asyncio
async def test_whatsapp_tenant_mapping_connect_time_duplicate_rejection(async_client, db_session, tenant_a, tenant_b):
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

    # Connect phone_number_id for Tenant A
    conn_a = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="whatsapp_cloud_api",
        credentials={"access_token": "token_a", "app_secret": "secret_a", "phone_number_id": phone_id},
        external_account_id=phone_id,
        allow_internal=True,
    )

    # Attempting to connect the same phone_number_id for Tenant B MUST fail-closed with PermanentIntegrationError
    with pytest.raises(PermanentIntegrationError) as excinfo:
        await service.connect_integration(
            tenant_id=tenant_b.id,
            integration_key="whatsapp_cloud_api",
            credentials={"access_token": "token_b", "app_secret": "secret_b", "phone_number_id": phone_id},
            external_account_id=phone_id,
            allow_internal=True,
        )
    assert excinfo.value.error_code == "ACCOUNT_ALREADY_CONNECTED"


@pytest.mark.asyncio
async def test_whatsapp_webhook_ambiguity_rejection(async_client, db_session, tenant_a, tenant_b):
    # Insert two active connections with different integrations sharing external_account_id
    integration1 = Integration(
        integration_key="whatsapp_cloud_api_a",
        provider_key="whatsapp_cloud_api",
        display_name="WhatsApp Cloud API A",
        tenant_id=tenant_a.id,
        is_enabled=True,
    )
    integration2 = Integration(
        integration_key="whatsapp_cloud_api_b",
        provider_key="whatsapp",
        display_name="WhatsApp Cloud API B",
        tenant_id=tenant_b.id,
        is_enabled=True,
    )
    db_session.add_all([integration1, integration2])
    await db_session.commit()

    phone_id = "duplicate_phone_number_999"

    conn_a = IntegrationConnection(
        tenant_id=tenant_a.id,
        integration_id=integration1.id,
        status="ACTIVE",
        external_account_id=phone_id,
    )
    conn_b = IntegrationConnection(
        tenant_id=tenant_b.id,
        integration_id=integration2.id,
        status="ACTIVE",
        external_account_id=phone_id,
    )
    db_session.add_all([conn_a, conn_b])
    await db_session.commit()

    service = IntegrationService(db_session)
    # Store credentials for both connections
    enc_a = service.vault.encrypt_credentials({"access_token": "a", "app_secret": "secret_a", "phone_number_id": phone_id})
    enc_b = service.vault.encrypt_credentials({"access_token": "b", "app_secret": "secret_b", "phone_number_id": phone_id})

    from app.database.models.integrations import IntegrationCredential
    cred_a = IntegrationCredential(tenant_id=tenant_a.id, connection_id=conn_a.id, credential_type="api_key", encrypted_secret=enc_a)
    cred_b = IntegrationCredential(tenant_id=tenant_b.id, connection_id=conn_b.id, credential_type="api_key", encrypted_secret=enc_b)
    db_session.add_all([cred_a, cred_b])
    await db_session.commit()

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

    # Ambiguous mapping should return HTTP 409 Conflict
    resp = await async_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert resp.status_code == 409
    assert "Ambiguous mapping" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_catalog_integration_singleton_enforcement(db_session):
    # System catalog integration (tenant_id IS NULL) with duplicate provider_key MUST fail unique constraint
    cat1 = Integration(
        tenant_id=None,
        integration_key="whatsapp_cloud_api_v1",
        provider_key="whatsapp_cloud_api",
        display_name="WhatsApp V1",
    )
    db_session.add(cat1)
    await db_session.commit()

    cat2 = Integration(
        tenant_id=None,
        integration_key="whatsapp_cloud_api_v2",
        provider_key="whatsapp_cloud_api",
        display_name="WhatsApp V2",
    )
    db_session.add(cat2)
    from sqlalchemy.exc import IntegrityError
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


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
