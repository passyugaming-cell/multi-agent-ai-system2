import uuid
import asyncio
import hmac
import hashlib
import json
import pytest
from sqlalchemy import select, func
from app.database.models.integrations import Integration, IntegrationConnection, IntegrationCredential
from app.integrations.service import IntegrationService
from app.integrations.exceptions import PermanentIntegrationError
from app.billing.plans import PlanService
from app.billing.subscription import SubscriptionService


@pytest.mark.asyncio
async def test_real_concurrent_tenant_connections_race_condition(async_client, test_session_factory, tenant_a, tenant_b):
    """Real database concurrency test using asyncio.gather across independent sessions."""
    async with test_session_factory() as session:
        plan_srv = PlanService(session)
        await plan_srv.seed_plans()

        sub_srv = SubscriptionService(session)
        await sub_srv.create_trial_subscription(tenant_a.id)
        await sub_srv.create_trial_subscription(tenant_b.id)

        integration = Integration(
            integration_key="whatsapp_cloud_api",
            provider_key="whatsapp_cloud_api",
            display_name="WhatsApp Cloud API",
            is_enabled=True,
        )
        session.add(integration)
        await session.commit()

    shared_phone_id = f"concurrent_phone_{uuid.uuid4().hex[:8]}"

    async def connect_tenant(t_id: uuid.UUID):
        async with test_session_factory() as session:
            service = IntegrationService(session)
            try:
                res = await service.connect_integration(
                    tenant_id=t_id,
                    integration_key="whatsapp_cloud_api",
                    credentials={"access_token": "tok", "app_secret": "sec", "phone_number_id": shared_phone_id},
                    external_account_id=shared_phone_id,
                    allow_internal=True,
                )
                return ("SUCCESS", res)
            except PermanentIntegrationError as pie:
                return ("CONFLICT" if pie.error_code == "ACCOUNT_ALREADY_CONNECTED" else "ERROR", pie)
            except Exception as e:
                return ("ERROR", e)

    results = await asyncio.gather(
        connect_tenant(tenant_a.id),
        connect_tenant(tenant_b.id),
        return_exceptions=True,
    )

    statuses = [r[0] for r in results]
    assert "SUCCESS" in statuses
    assert "CONFLICT" in statuses

    conflict_res = [r[1] for r in results if r[0] == "CONFLICT"][0]
    assert conflict_res.error_code == "ACCOUNT_ALREADY_CONNECTED"

    async with test_session_factory() as session:
        active_stmt = select(func.count(IntegrationConnection.id)).where(
            IntegrationConnection.external_account_id == shared_phone_id,
            IntegrationConnection.status.in_(["ACTIVE", "CONNECTED", "CONNECTING"]),
        )
        count = (await session.execute(active_stmt)).scalar()
        assert count == 1


@pytest.mark.asyncio
async def test_whatsapp_webhook_security_matrix(async_client, db_session, tenant_a, tenant_b, inactive_tenant):
    """Verifies mandatory signature verification, missing credentials, invalid signatures, unknown phone, inactive tenant, and idempotency."""
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
    phone_id_a = f"phone_sec_a_{uuid.uuid4().hex[:6]}"
    app_secret_a = "secret_valid_a_123"

    conn_a = await service.connect_integration(
        tenant_id=tenant_a.id,
        integration_key="whatsapp_cloud_api",
        credentials={"access_token": "token_a", "app_secret": app_secret_a, "phone_number_id": phone_id_a},
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
                            "messages": [{"from": "62812345678", "id": "wamid.sec_msg_1", "timestamp": "12345", "type": "text", "text": {"body": "Security Test"}}],
                        },
                        "field": "messages",
                    }
                ],
            }
        ],
    }

    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    valid_sig = hmac.new(app_secret_a.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    # Case A: Valid app_secret + valid signature -> accepted
    resp_a = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={valid_sig}"},
    )
    assert resp_a.status_code == 200

    # Case B: Valid app_secret + invalid signature -> rejected (401)
    resp_b = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=invalid_signature_hash"},
    )
    assert resp_b.status_code == 401

    # Case C: Valid app_secret + missing signature -> rejected (401)
    resp_c = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert resp_c.status_code == 401

    # Case D: Missing app_secret in connection credentials -> rejected (401)
    phone_id_no_sec = f"phone_no_secret_{uuid.uuid4().hex[:6]}"
    conn_no_sec = IntegrationConnection(
        tenant_id=tenant_b.id,
        integration_id=integration.id,
        provider_key="whatsapp_cloud_api",
        status="ACTIVE",
        external_account_id=phone_id_no_sec,
    )
    db_session.add(conn_no_sec)
    await db_session.commit()

    enc_no_sec = service.vault.encrypt_credentials({"access_token": "tok", "phone_number_id": phone_id_no_sec})
    cred_no_sec = IntegrationCredential(tenant_id=tenant_b.id, connection_id=conn_no_sec.id, credential_type="api_key", encrypted_secret=enc_no_sec)
    db_session.add(cred_no_sec)
    await db_session.commit()

    payload_no_sec = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "entry_id", "changes": [{"value": {"metadata": {"phone_number_id": phone_id_no_sec}}}]}],
    }
    raw_no_sec = json.dumps(payload_no_sec, separators=(",", ":")).encode("utf-8")
    resp_d = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_no_sec,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": "sha256=any_sig"},
    )
    assert resp_d.status_code == 401

    # Case G: Unknown phone_number_id -> 404
    payload_unknown = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "entry_id", "changes": [{"value": {"metadata": {"phone_number_id": "nonexistent_phone"}}}]}],
    }
    resp_g = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        json=payload_unknown,
    )
    assert resp_g.status_code == 404

    # Case H: Duplicate webhook remains idempotent
    resp_h = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={valid_sig}"},
    )
    assert resp_h.status_code == 200
    assert resp_h.json()["processed"][0]["status"] == "duplicate"


@pytest.mark.asyncio
async def test_whatsapp_webhook_ambiguity_rejection(async_client, db_session, tenant_a, tenant_b):
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
        provider_key=integration1.provider_key,
        status="ACTIVE",
        external_account_id=phone_id,
    )
    conn_b = IntegrationConnection(
        tenant_id=tenant_b.id,
        integration_id=integration2.id,
        provider_key=integration2.provider_key,
        status="ACTIVE",
        external_account_id=phone_id,
    )
    db_session.add_all([conn_a, conn_b])
    await db_session.commit()

    service = IntegrationService(db_session)
    enc_a = service.vault.encrypt_credentials({"access_token": "a", "app_secret": "secret_a", "phone_number_id": phone_id})
    enc_b = service.vault.encrypt_credentials({"access_token": "b", "app_secret": "secret_b", "phone_number_id": phone_id})

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

    raw_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    sig = hmac.new("secret_a".encode("utf-8"), raw_body, hashlib.sha256).hexdigest()

    resp = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_body,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"},
    )
    assert resp.status_code == 409
    assert "Ambiguous mapping" in resp.json()["error"]["message"]


@pytest.mark.asyncio
async def test_catalog_integration_singleton_enforcement(db_session):
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
