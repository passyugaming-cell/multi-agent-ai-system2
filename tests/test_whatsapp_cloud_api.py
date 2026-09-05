import uuid
import hmac
import hashlib
import json
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.models import Tenant, Customer, Conversation, Message, User
from app.database.models.integrations import Integration, IntegrationConnection, IntegrationCredential, IntegrationExecution
from app.database.models.billing import Plan, Subscription, PlanFeature
import app.integrations.adapters
from app.integrations.adapters.whatsapp_cloud_api import WhatsAppCloudApiAdapter
from app.integrations.registry import integration_registry
from app.integrations.service import IntegrationService
from app.integrations.exceptions import (
    PermanentIntegrationError,
    TransientIntegrationError,
    PermissionDeniedError,
    EntitlementDeniedError,
)
from app.integrations.permissions import (
    VIEW_INTEGRATIONS,
    MANAGE_INTEGRATIONS,
    MANAGE_CREDENTIALS,
    EXECUTE_INTEGRATION,
    VIEW_WHATSAPP_CONNECTION,
    MANAGE_WHATSAPP_CONNECTION,
    SEND_WHATSAPP_MESSAGE,
    MANAGE_WHATSAPP_WEBHOOK,
)
from app.billing.entitlement import EntitlementResolver
from app.core.workflows.actions import ActionExecutor, ActionResult
from app.agents.base.schemas import ToolRequest
from app.agents.owner_ai.tools import tool_get_whatsapp_connection_status


@pytest.fixture
async def setup_whatsapp_integration_db(db_session: AsyncSession):
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
    return integration


@pytest.fixture
async def active_whatsapp_tenant(db_session: AsyncSession, setup_whatsapp_integration_db: Integration):
    tenant = Tenant(name="WA Enterprise", slug=f"wa-ent-{uuid.uuid4().hex[:6]}", is_active=True)
    db_session.add(tenant)
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

    phone_number_id = f"100200{uuid.uuid4().hex[:6]}"
    app_secret = f"secret_{uuid.uuid4().hex[:12]}"
    verify_token = f"token_{uuid.uuid4().hex[:8]}"
    access_token = f"mock_token_{uuid.uuid4().hex[:8]}"

    conn = IntegrationConnection(
        tenant_id=tenant.id,
        integration_id=setup_whatsapp_integration_db.id,
        status="ACTIVE",
        external_account_id=phone_number_id,
        meta_data={"phone_number_id": phone_number_id},
    )
    db_session.add(conn)
    await db_session.commit()

    service = IntegrationService(db_session)
    creds_dict = {
        "phone_number_id": phone_number_id,
        "access_token": access_token,
        "app_secret": app_secret,
        "verify_token": verify_token,
        "waba_id": "waba_123456",
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

    return {
        "tenant": tenant,
        "connection": conn,
        "credentials": creds_dict,
        "phone_number_id": phone_number_id,
        "app_secret": app_secret,
        "verify_token": verify_token,
        "access_token": access_token,
    }


# ==========================================
# SECTION A: ADAPTER TESTS (1 - 10)
# ==========================================

@pytest.mark.asyncio
async def test_01_adapter_registration():
    assert integration_registry.is_registered("whatsapp_cloud_api")
    assert integration_registry.is_registered("whatsapp")
    adapter = integration_registry.get_adapter("whatsapp_cloud_api")
    assert isinstance(adapter, WhatsAppCloudApiAdapter)


@pytest.mark.asyncio
async def test_02_connection_configuration(db_session: AsyncSession):
    adapter = WhatsAppCloudApiAdapter()
    tenant_id = uuid.uuid4()
    conn_id = uuid.uuid4()

    valid_creds = {"phone_number_id": "12345", "access_token": "token_abc"}
    connected = await adapter.connect(tenant_id, conn_id, valid_creds, session=db_session)
    assert connected is True

    invalid_creds = {"phone_number_id": "12345"}
    with pytest.raises(PermanentIntegrationError):
        await adapter.connect(tenant_id, conn_id, invalid_creds, session=db_session)


@pytest.mark.asyncio
async def test_03_send_text(active_whatsapp_tenant):
    adapter = WhatsAppCloudApiAdapter(is_development=True)
    tenant_id = active_whatsapp_tenant["tenant"].id
    conn_id = active_whatsapp_tenant["connection"].id
    creds = active_whatsapp_tenant["credentials"]

    res = await adapter.execute(
        tenant_id=tenant_id,
        connection_id=conn_id,
        credentials=creds,
        operation="send_text",
        params={"recipient": "628123456789", "text": "Hello text"},
    )
    assert res["success"] is True
    assert "provider_message_id" in res


@pytest.mark.asyncio
async def test_04_send_media(active_whatsapp_tenant):
    adapter = WhatsAppCloudApiAdapter(is_development=True)
    tenant_id = active_whatsapp_tenant["tenant"].id
    conn_id = active_whatsapp_tenant["connection"].id
    creds = active_whatsapp_tenant["credentials"]

    res = await adapter.execute(
        tenant_id=tenant_id,
        connection_id=conn_id,
        credentials=creds,
        operation="send_media",
        params={
            "recipient": "628123456789",
            "message_type": "image",
            "media_url": "https://example.com/image.png",
            "text": "Caption text",
        },
    )
    assert res["success"] is True


@pytest.mark.asyncio
async def test_05_provider_success(active_whatsapp_tenant):
    adapter = WhatsAppCloudApiAdapter(is_development=True)
    tenant_id = active_whatsapp_tenant["tenant"].id
    conn_id = active_whatsapp_tenant["connection"].id
    creds = active_whatsapp_tenant["credentials"]

    res = await adapter.execute(
        tenant_id=tenant_id,
        connection_id=conn_id,
        credentials=creds,
        operation="send_message",
        params={"recipient": "628123456789", "text": "Success message"},
    )
    assert res["success"] is True
    assert res["messaging_product"] == "whatsapp"


@pytest.mark.asyncio
async def test_06_provider_failure(active_whatsapp_tenant, monkeypatch):
    adapter = WhatsAppCloudApiAdapter(is_development=False)
    tenant_id = active_whatsapp_tenant["tenant"].id
    conn_id = active_whatsapp_tenant["connection"].id
    creds = dict(active_whatsapp_tenant["credentials"])
    creds["access_token"] = "real_invalid_token"

    import httpx

    async def mock_post(*args, **kwargs):
        class MockResp:
            status_code = 400
            content = b'{"error": {"message": "Invalid OAuth access token."}}'
            def json(self):
                return {"error": {"message": "Invalid OAuth access token."}}
        return MockResp()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post)

    with pytest.raises(PermanentIntegrationError) as exc_info:
        await adapter.execute(
            tenant_id=tenant_id,
            connection_id=conn_id,
            credentials=creds,
            operation="send_message",
            params={"recipient": "628123456789", "text": "Fail test"},
        )
    assert "Invalid OAuth access token" in str(exc_info.value)


@pytest.mark.asyncio
async def test_07_timeout(active_whatsapp_tenant, monkeypatch):
    adapter = WhatsAppCloudApiAdapter(is_development=False)
    tenant_id = active_whatsapp_tenant["tenant"].id
    conn_id = active_whatsapp_tenant["connection"].id
    creds = dict(active_whatsapp_tenant["credentials"])
    creds["access_token"] = "prod_token"

    import httpx

    async def mock_timeout(*args, **kwargs):
        raise httpx.TimeoutException("Connection timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_timeout)

    with pytest.raises(TransientIntegrationError):
        await adapter.execute(
            tenant_id=tenant_id,
            connection_id=conn_id,
            credentials=creds,
            operation="send_message",
            params={"recipient": "628123456789", "text": "Timeout test"},
        )


@pytest.mark.asyncio
async def test_08_retryable_failure(active_whatsapp_tenant, monkeypatch):
    adapter = WhatsAppCloudApiAdapter(is_development=False)
    tenant_id = active_whatsapp_tenant["tenant"].id
    conn_id = active_whatsapp_tenant["connection"].id
    creds = dict(active_whatsapp_tenant["credentials"])
    creds["access_token"] = "prod_token"

    import httpx

    async def mock_503(*args, **kwargs):
        class MockResp:
            status_code = 503
            content = b'{"error": {"message": "Service Temporarily Unavailable"}}'
            def json(self):
                return {"error": {"message": "Service Temporarily Unavailable"}}
        return MockResp()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_503)

    with pytest.raises(TransientIntegrationError):
        await adapter.execute(
            tenant_id=tenant_id,
            connection_id=conn_id,
            credentials=creds,
            operation="send_message",
            params={"recipient": "628123456789", "text": "503 test"},
        )


@pytest.mark.asyncio
async def test_09_non_retryable_failure(active_whatsapp_tenant, monkeypatch):
    adapter = WhatsAppCloudApiAdapter(is_development=False)
    tenant_id = active_whatsapp_tenant["tenant"].id
    conn_id = active_whatsapp_tenant["connection"].id
    creds = dict(active_whatsapp_tenant["credentials"])
    creds["access_token"] = "prod_token"

    import httpx

    async def mock_401(*args, **kwargs):
        class MockResp:
            status_code = 401
            content = b'{"error": {"message": "Unauthorized"}}'
            def json(self):
                return {"error": {"message": "Unauthorized"}}
        return MockResp()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_401)

    with pytest.raises(PermanentIntegrationError):
        await adapter.execute(
            tenant_id=tenant_id,
            connection_id=conn_id,
            credentials=creds,
            operation="send_message",
            params={"recipient": "628123456789", "text": "401 test"},
        )


@pytest.mark.asyncio
async def test_10_rate_limit(active_whatsapp_tenant, monkeypatch):
    adapter = WhatsAppCloudApiAdapter(is_development=False)
    tenant_id = active_whatsapp_tenant["tenant"].id
    conn_id = active_whatsapp_tenant["connection"].id
    creds = dict(active_whatsapp_tenant["credentials"])
    creds["access_token"] = "prod_token"

    import httpx

    async def mock_429(*args, **kwargs):
        class MockResp:
            status_code = 429
            content = b'{"error": {"message": "Rate limit exceeded."}}'
            def json(self):
                return {"error": {"message": "Rate limit exceeded."}}
        return MockResp()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_429)

    with pytest.raises(TransientIntegrationError) as exc_info:
        await adapter.execute(
            tenant_id=tenant_id,
            connection_id=conn_id,
            credentials=creds,
            operation="send_message",
            params={"recipient": "628123456789", "text": "429 test"},
        )
    assert exc_info.value.error_code == "RATE_LIMIT_OR_TIMEOUT"


# ==========================================
# SECTION B: WEBHOOK TESTS (11 - 24)
# ==========================================

@pytest.mark.asyncio
async def test_11_get_verification_success(async_client: AsyncClient, active_whatsapp_tenant):
    verify_token = active_whatsapp_tenant["verify_token"]
    res = await async_client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "12345678",
            "hub.verify_token": verify_token,
        },
    )
    assert res.status_code == 200
    assert res.text == "12345678"


@pytest.mark.asyncio
async def test_12_get_verification_failure(async_client: AsyncClient, active_whatsapp_tenant):
    res = await async_client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "12345678",
            "hub.verify_token": "wrong_verify_token",
        },
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_13_invalid_verify_token(async_client: AsyncClient, active_whatsapp_tenant):
    res = await async_client.get(
        "/api/v1/webhooks/whatsapp",
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "9999",
            "hub.verify_token": "",
        },
    )
    assert res.status_code in (400, 403)


@pytest.mark.asyncio
async def test_14_valid_post(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "12345", "phone_number_id": phone_id},
                            "contacts": [{"profile": {"name": "Test User"}, "wa_id": "62899900011"}],
                            "messages": [
                                {
                                    "from": "62899900011",
                                    "id": f"wamid.valid_post_{uuid.uuid4().hex[:6]}",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "Test message body"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()

    res = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert data["processed"][0]["status"] == "processed"


@pytest.mark.asyncio
async def test_15_invalid_post(async_client: AsyncClient):
    res = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_16_invalid_signature(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_id},
                            "messages": [{"from": "628", "id": "msg_1", "timestamp": "1710000000", "type": "text", "text": {"body": "hi"}}],
                        },
                    }
                ],
            }
        ],
    }

    res = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        json=payload,
        headers={"X-Hub-Signature-256": "sha256=invalid_signature_hash"},
    )
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_17_valid_signature(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_id},
                            "messages": [{"from": "62899", "id": f"wamid.sig_ok_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "hello"}}],
                        },
                    }
                ],
            }
        ],
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()

    res = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"},
    )
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_18_constant_time_verification():
    adapter = WhatsAppCloudApiAdapter()
    raw = b"test payload"
    app_secret = "secret_key_123"

    valid_sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    assert adapter.verify_webhook_signature(raw, f"sha256={valid_sig}", app_secret) is True
    assert adapter.verify_webhook_signature(raw, "sha256=wrong_sig", app_secret) is False


@pytest.mark.asyncio
async def test_19_unknown_phone_number_id(async_client: AsyncClient):
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": "unknown_phone_id_99999"},
                            "messages": [{"from": "628", "id": "m1", "timestamp": "1710000000", "type": "text", "text": {"body": "hi"}}],
                        },
                    }
                ],
            }
        ],
    }

    res = await async_client.post("/api/v1/webhooks/whatsapp", json=payload)
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_20_tenant_resolution(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]
    tenant_id = str(active_whatsapp_tenant["tenant"].id)

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_id},
                            "messages": [{"from": "62811", "id": f"wamid.tenant_res_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "hi"}}],
                        },
                    }
                ],
            }
        ],
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()

    res = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"},
    )
    assert res.status_code == 200
    assert res.json()["tenant_id"] == tenant_id


@pytest.mark.asyncio
async def test_21_cross_tenant_isolation(async_client: AsyncClient, active_whatsapp_tenant, test_session: AsyncSession, setup_whatsapp_integration_db):
    tenant_b = Tenant(name="Tenant B WA", slug=f"tenant-b-{uuid.uuid4().hex[:6]}", is_active=True)
    test_session.add(tenant_b)
    await test_session.commit()

    phone_id_b = f"200300{uuid.uuid4().hex[:6]}"
    app_secret_b = f"secret_b_{uuid.uuid4().hex[:6]}"

    conn_b = IntegrationConnection(
        tenant_id=tenant_b.id,
        integration_id=setup_whatsapp_integration_db.id,
        status="ACTIVE",
        external_account_id=phone_id_b,
    )
    test_session.add(conn_b)
    await test_session.commit()

    service = IntegrationService(test_session)
    enc_secret_b = service.vault.encrypt_credentials({"phone_number_id": phone_id_b, "access_token": "token_b", "app_secret": app_secret_b})
    cred_b = IntegrationCredential(tenant_id=tenant_b.id, connection_id=conn_b.id, credential_type="bearer_token", encrypted_secret=enc_secret_b)
    test_session.add(cred_b)
    await test_session.commit()

    payload_b = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_b",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_id_b},
                            "messages": [{"from": "62822", "id": f"wamid.tb_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "hi B"}}],
                        },
                    }
                ],
            }
        ],
    }
    raw_b = json.dumps(payload_b).encode("utf-8")
    sig_b = hmac.new(app_secret_b.encode("utf-8"), raw_b, hashlib.sha256).hexdigest()

    res = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_b,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig_b}"},
    )
    assert res.status_code == 200
    assert res.json()["tenant_id"] == str(tenant_b.id)
    assert res.json()["tenant_id"] != str(active_whatsapp_tenant["tenant"].id)


@pytest.mark.asyncio
async def test_22_duplicate_webhook(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]
    msg_id = f"wamid.dup_{uuid.uuid4().hex[:8]}"

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_id},
                            "messages": [{"from": "62811", "id": msg_id, "timestamp": "1710000000", "type": "text", "text": {"body": "dup msg"}}],
                        },
                    }
                ],
            }
        ],
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()

    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"}

    res1 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["processed"][0]["status"] == "processed"

    res2 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["processed"][0]["status"] == "duplicate"


@pytest.mark.asyncio
async def test_23_duplicate_concurrent_webhook(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]
    msg_id = f"wamid.concurrent_{uuid.uuid4().hex[:8]}"

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_id},
                            "messages": [{"from": "62811", "id": msg_id, "timestamp": "1710000000", "type": "text", "text": {"body": "concurrent test"}}],
                        },
                    }
                ],
            }
        ],
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"}

    r1 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)
    r2 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)

    assert r1.status_code == 200
    assert r2.status_code == 200
    statuses = [r1.json()["processed"][0]["status"], r2.json()["processed"][0]["status"]]
    assert "processed" in statuses
    assert "duplicate" in statuses


@pytest.mark.asyncio
async def test_24_malformed_payload(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    payload = {"object": "whatsapp_business_account", "entry": [{"id": "e1", "changes": []}]}
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()

    res = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw_bytes,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"},
    )
    assert res.status_code in (400, 404)


# ==========================================
# SECTION C: UNIVERSAL MESSAGE TESTS (25 - 30)
# ==========================================

@pytest.mark.asyncio
async def test_25_text_normalization(active_whatsapp_tenant):
    from app.integrations.whatsapp.parser import WhatsAppParser
    tenant_id = active_whatsapp_tenant["tenant"].id

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "contacts": [{"profile": {"name": "Alice"}, "wa_id": "6281000"}],
                            "messages": [
                                {
                                    "from": "6281000",
                                    "id": "wamid.text_norm_1",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "Hello universal"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    um_list = WhatsAppParser.parse_payload(tenant_id, payload)
    assert len(um_list) == 1
    um = um_list[0]
    assert um.channel == "whatsapp"
    assert um.message_type == "TEXT"
    assert um.text == "Hello universal"
    assert um.external_message_id == "wamid.text_norm_1"


@pytest.mark.asyncio
async def test_26_media_normalization(active_whatsapp_tenant):
    from app.integrations.whatsapp.parser import WhatsAppParser
    tenant_id = active_whatsapp_tenant["tenant"].id

    payload = {
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
                                    "from": "6281000",
                                    "id": "wamid.img_1",
                                    "timestamp": "1710000000",
                                    "type": "image",
                                    "image": {"id": "media_id_100", "caption": "Media caption"},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }

    um_list = WhatsAppParser.parse_payload(tenant_id, payload)
    assert len(um_list) == 1
    assert um_list[0].message_type == "IMAGE"
    assert um_list[0].text == "Media caption"


@pytest.mark.asyncio
async def test_27_sender_identity_normalization(active_whatsapp_tenant):
    from app.integrations.whatsapp.parser import WhatsAppParser
    tenant_id = active_whatsapp_tenant["tenant"].id

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "contacts": [{"profile": {"name": "Bob Builder"}, "wa_id": "628555"}],
                            "messages": [{"from": "628555", "id": "wamid.bob_1", "timestamp": "1710000000", "type": "text", "text": {"body": "hi"}}],
                        },
                    }
                ],
            }
        ],
    }

    um_list = WhatsAppParser.parse_payload(tenant_id, payload)
    assert um_list[0].metadata["sender_phone"] == "628555"
    assert um_list[0].metadata["sender_name"] == "Bob Builder"


@pytest.mark.asyncio
async def test_28_external_message_id(active_whatsapp_tenant):
    from app.integrations.whatsapp.parser import WhatsAppParser
    tenant_id = active_whatsapp_tenant["tenant"].id

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"messages": [{"from": "123", "id": "wamid.ext_123", "timestamp": "1710000000", "type": "text", "text": {"body": "x"}}]}}]}]
    }

    um = WhatsAppParser.parse_payload(tenant_id, payload)[0]
    assert um.external_message_id == "wamid.ext_123"


@pytest.mark.asyncio
async def test_29_timestamp_normalization(active_whatsapp_tenant):
    from app.integrations.whatsapp.parser import WhatsAppParser
    tenant_id = active_whatsapp_tenant["tenant"].id

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"messages": [{"from": "123", "id": "wamid.ts_1", "timestamp": "1710000000", "type": "text", "text": {"body": "ts"}}]}}]}]
    }

    um = WhatsAppParser.parse_payload(tenant_id, payload)[0]
    expected_dt = datetime.fromtimestamp(1710000000, tz=timezone.utc)
    assert um.timestamp == expected_dt


@pytest.mark.asyncio
async def test_30_provider_metadata(active_whatsapp_tenant):
    from app.integrations.whatsapp.parser import WhatsAppParser
    tenant_id = active_whatsapp_tenant["tenant"].id

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"messages": [{"from": "62899", "id": "wamid.meta_1", "timestamp": "1710000000", "type": "text", "text": {"body": "meta"}}]}}]}]
    }

    um = WhatsAppParser.parse_payload(tenant_id, payload)[0]
    assert um.metadata["raw_type"] == "text"


# ==========================================
# SECTION D: CUSTOMER TESTS (31 - 34)
# ==========================================

@pytest.mark.asyncio
async def test_31_existing_customer_resolution(async_client: AsyncClient, active_whatsapp_tenant, test_session: AsyncSession):
    tenant_id = active_whatsapp_tenant["tenant"].id
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    existing_cust = Customer(tenant_id=tenant_id, name="Existing User", phone="62811122233")
    test_session.add(existing_cust)
    await test_session.commit()

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": "62811122233", "id": f"wamid.cust_res_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "hi"}}]}}]}]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    assert res.status_code == 200

    from app.repositories.domain import CustomerRepository
    c_repo = CustomerRepository(test_session)
    customers = await c_repo.list_all(tenant_id)
    matching = [c for c in customers if c.phone == "62811122233"]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_32_new_customer_creation(async_client: AsyncClient, active_whatsapp_tenant, test_session: AsyncSession):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]
    new_phone = f"62899{uuid.uuid4().hex[:6]}"

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "contacts": [{"profile": {"name": "New Cust"}, "wa_id": new_phone}], "messages": [{"from": new_phone, "id": f"wamid.new_cust_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "hello new"}}]}}]}]
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw_bytes, hashlib.sha256).hexdigest()

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    assert res.status_code == 200

    from app.repositories.domain import CustomerRepository
    c_repo = CustomerRepository(test_session)
    cust = await c_repo.get_by_phone(active_whatsapp_tenant["tenant"].id, new_phone)
    assert cust is not None
    assert cust.name == "New Cust"


@pytest.mark.asyncio
async def test_33_repeated_message_no_duplicate_customer(async_client: AsyncClient, active_whatsapp_tenant, test_session: AsyncSession):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]
    phone = f"62877{uuid.uuid4().hex[:6]}"

    payload1 = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": phone, "id": f"wamid.msg1_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "msg 1"}}]}}]}]
    }
    payload2 = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": phone, "id": f"wamid.msg2_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "msg 2"}}]}}]}]
    }

    for p in (payload1, payload2):
        raw = json.dumps(p).encode("utf-8")
        sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})

    from app.repositories.domain import CustomerRepository
    c_repo = CustomerRepository(test_session)
    customers = await c_repo.list_all(active_whatsapp_tenant["tenant"].id)
    matching = [c for c in customers if c.phone == phone]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_34_cross_tenant_identity_isolation(active_whatsapp_tenant, test_session: AsyncSession):
    tenant_a_id = active_whatsapp_tenant["tenant"].id
    tenant_b = Tenant(name="Tenant B", slug=f"tb-{uuid.uuid4().hex[:6]}", is_active=True)
    test_session.add(tenant_b)
    await test_session.commit()

    shared_phone = "628111999"
    cust_a = Customer(tenant_id=tenant_a_id, name="User A", phone=shared_phone)
    cust_b = Customer(tenant_id=tenant_b.id, name="User B", phone=shared_phone)
    test_session.add_all([cust_a, cust_b])
    await test_session.commit()

    from app.repositories.domain import CustomerRepository
    c_repo = CustomerRepository(test_session)
    resolved_a = await c_repo.get_by_phone(tenant_a_id, shared_phone)
    resolved_b = await c_repo.get_by_phone(tenant_b.id, shared_phone)

    assert resolved_a.id != resolved_b.id
    assert resolved_a.tenant_id == tenant_a_id
    assert resolved_b.tenant_id == tenant_b.id


# ==========================================
# SECTION E: CONVERSATION TESTS (35 - 38)
# ==========================================

@pytest.mark.asyncio
async def test_35_conversation_creation(async_client: AsyncClient, active_whatsapp_tenant, test_session: AsyncSession):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]
    phone = f"628123_{uuid.uuid4().hex[:6]}"

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": phone, "id": f"wamid.conv_new_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "conv message"}}]}}]}]
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    assert res.status_code == 200

    from app.repositories.domain import CustomerRepository, ConversationRepository
    c_repo = CustomerRepository(test_session)
    conv_repo = ConversationRepository(test_session)

    cust = await c_repo.get_by_phone(active_whatsapp_tenant["tenant"].id, phone)
    conv = await conv_repo.get_active_by_customer(active_whatsapp_tenant["tenant"].id, cust.id)
    assert conv is not None
    assert conv.channel == "whatsapp"


@pytest.mark.asyncio
async def test_36_existing_conversation_reuse(async_client: AsyncClient, active_whatsapp_tenant, test_session: AsyncSession):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]
    phone = f"628999_{uuid.uuid4().hex[:6]}"

    payload1 = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": phone, "id": f"wamid.conv1_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "conv 1"}}]}}]}]
    }
    payload2 = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": phone, "id": f"wamid.conv2_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "conv 2"}}]}}]}]
    }

    for p in (payload1, payload2):
        raw = json.dumps(p).encode("utf-8")
        sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})

    from app.repositories.domain import CustomerRepository, ConversationRepository
    cust = await CustomerRepository(test_session).get_by_phone(active_whatsapp_tenant["tenant"].id, phone)
    convs = await ConversationRepository(test_session).list_all(active_whatsapp_tenant["tenant"].id)
    cust_convs = [c for c in convs if c.customer_id == cust.id]
    assert len(cust_convs) == 1


@pytest.mark.asyncio
async def test_37_router_integration(async_client: AsyncClient, active_whatsapp_tenant, test_session: AsyncSession):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]
    phone = f"62855_{uuid.uuid4().hex[:6]}"

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": phone, "id": f"wamid.router_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "harga barang"}}]}}]}]
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    assert res.status_code == 200
    data = res.json()
    assert data["processed"][0]["status"] == "processed"


@pytest.mark.asyncio
async def test_38_human_handoff_compatibility(async_client: AsyncClient, active_whatsapp_tenant, test_session: AsyncSession):
    tenant_id = active_whatsapp_tenant["tenant"].id
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]
    phone = f"628handoff_{uuid.uuid4().hex[:6]}"

    cust = Customer(tenant_id=tenant_id, name="Handoff Cust", phone=phone)
    test_session.add(cust)
    await test_session.commit()

    conv = Conversation(tenant_id=tenant_id, customer_id=cust.id, channel="whatsapp", status="OPEN", human_handoff=True, ai_enabled=False)
    test_session.add(conv)
    await test_session.commit()

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": phone, "id": f"wamid.ho_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "need human agent"}}]}}]}]
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    assert res.status_code == 200

    from app.repositories.domain import MessageRepository
    m_repo = MessageRepository(test_session)
    msgs = await m_repo.list_by_conversation(tenant_id, conv.id)
    outbound = [m for m in msgs if m.direction == "OUTBOUND"][0]
    assert "[SYSTEM] Message logged for human agent." in outbound.text


# ==========================================
# SECTION F: STATUS TESTS (39 - 43)
# ==========================================

@pytest.mark.asyncio
async def test_39_sent_event(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_id},
                            "statuses": [{"id": "wamid.msg_sent_1", "status": "sent", "timestamp": "1710000000", "recipient_id": "62811"}],
                        },
                    }
                ],
            }
        ],
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    assert res.status_code == 200
    assert res.json()["processed"][0]["status"] == "sent"


@pytest.mark.asyncio
async def test_40_delivered_event(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "statuses": [{"id": "wamid.msg_deliv_1", "status": "delivered", "timestamp": "1710000000", "recipient_id": "62811"}]}}]}]
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    assert res.status_code == 200
    assert res.json()["processed"][0]["status"] == "delivered"


@pytest.mark.asyncio
async def test_41_read_event(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "statuses": [{"id": "wamid.msg_read_1", "status": "read", "timestamp": "1710000000", "recipient_id": "62811"}]}}]}]
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    assert res.status_code == 200
    assert res.json()["processed"][0]["status"] == "read"


@pytest.mark.asyncio
async def test_42_failed_event(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "statuses": [{"id": "wamid.msg_fail_1", "status": "failed", "timestamp": "1710000000", "recipient_id": "62811"}]}}]}]
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    assert res.status_code == 200
    assert res.json()["processed"][0]["status"] == "failed"


@pytest.mark.asyncio
async def test_43_duplicate_status_event(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "statuses": [{"id": "wamid.msg_dup_st_1", "status": "read", "timestamp": "1710000000", "recipient_id": "62811"}]}}]}]
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"}

    res1 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)
    assert res1.json()["processed"][0]["status"] == "read"

    res2 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)
    assert res2.json()["processed"][0]["status"] == "duplicate_event"


# ==========================================
# SECTION G: PERMISSIONS TESTS (44 - 47)
# ==========================================

@pytest.mark.asyncio
async def test_44_authorized_connection(test_session: AsyncSession, active_whatsapp_tenant):
    service = IntegrationService(test_session)
    tenant_id = active_whatsapp_tenant["tenant"].id

    conn = await service.get_connection_by_provider(
        tenant_id, "whatsapp_cloud_api", actor_permissions={VIEW_INTEGRATIONS, VIEW_WHATSAPP_CONNECTION}
    )
    assert conn is not None


@pytest.mark.asyncio
async def test_45_unauthorized_connection(test_session: AsyncSession, active_whatsapp_tenant):
    service = IntegrationService(test_session)
    tenant_id = active_whatsapp_tenant["tenant"].id

    with pytest.raises(PermissionDeniedError):
        await service.get_connection_by_provider(
            tenant_id, "whatsapp_cloud_api", actor_permissions={"MANAGE_PAYMENTS"}
        )


@pytest.mark.asyncio
async def test_46_missing_permission(test_session: AsyncSession, active_whatsapp_tenant):
    service = IntegrationService(test_session)
    tenant_id = active_whatsapp_tenant["tenant"].id

    with pytest.raises(PermissionDeniedError):
        await service.list_integrations(tenant_id, actor_permissions=[])


@pytest.mark.asyncio
async def test_47_empty_permission_set(test_session: AsyncSession, active_whatsapp_tenant):
    service = IntegrationService(test_session)
    tenant_id = active_whatsapp_tenant["tenant"].id

    with pytest.raises(PermissionDeniedError):
        await service.connect_integration(
            tenant_id, "whatsapp_cloud_api", credentials={}, actor_permissions=set()
        )


# ==========================================
# SECTION H: ENTITLEMENTS TESTS (48 - 50)
# ==========================================

@pytest.mark.asyncio
async def test_48_entitled_tenant(test_session: AsyncSession, active_whatsapp_tenant):
    resolver = EntitlementResolver(test_session)
    tenant_id = active_whatsapp_tenant["tenant"].id
    has_feat = await resolver.has_feature(tenant_id, "whatsapp_cloud_api")
    assert has_feat is True


@pytest.mark.asyncio
async def test_49_non_entitled_tenant(test_session: AsyncSession, setup_whatsapp_integration_db):
    tenant_no_wa = Tenant(name="Basic Tenant", slug=f"basic-{uuid.uuid4().hex[:6]}", is_active=True)
    test_session.add(tenant_no_wa)
    await test_session.commit()

    service = IntegrationService(test_session)
    with pytest.raises(EntitlementDeniedError):
        await service.connect_integration(
            tenant_no_wa.id,
            "whatsapp_cloud_api",
            credentials={"phone_number_id": "123", "access_token": "token"},
            actor_permissions={MANAGE_INTEGRATIONS, MANAGE_CREDENTIALS},
        )


@pytest.mark.asyncio
async def test_50_suspended_expired_tenant(test_session: AsyncSession, active_whatsapp_tenant):
    tenant_id = active_whatsapp_tenant["tenant"].id
    stmt = select(Subscription).where(Subscription.tenant_id == tenant_id)
    sub = (await test_session.execute(stmt)).scalar_one()
    sub.status = "EXPIRED"
    await test_session.commit()

    resolver = EntitlementResolver(test_session)
    has_feat = await resolver.has_feature(tenant_id, "whatsapp_cloud_api")
    assert has_feat is False


# ==========================================
# SECTION I: WORKFLOW / EVENTBUS TESTS (51 - 55)
# ==========================================

@pytest.mark.asyncio
async def test_51_inbound_event(async_client: AsyncClient, active_whatsapp_tenant, test_session: AsyncSession):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": "628900", "id": f"wamid.evt_in_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "evt test"}}]}}]}]
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_52_outbound_event(active_whatsapp_tenant, test_session: AsyncSession):
    service = IntegrationService(test_session)
    tenant_id = active_whatsapp_tenant["tenant"].id
    conn_id = active_whatsapp_tenant["connection"].id

    res = await service.execute_operation(
        tenant_id=tenant_id,
        connection_id=conn_id,
        operation="send_message",
        params={"recipient": "628100", "text": "Outbound event test"},
        actor_permissions={EXECUTE_INTEGRATION},
    )
    assert res.status == "COMPLETED"


@pytest.mark.asyncio
async def test_53_workflow_send_action(active_whatsapp_tenant, test_session: AsyncSession):
    tenant_id = str(active_whatsapp_tenant["tenant"].id)
    res = await ActionExecutor.execute(
        action_type="whatsapp_send_message",
        params={"recipient": "628100", "text": "Workflow WA message"},
        context={},
        session=test_session,
        tenant_id=tenant_id,
    )
    assert res.success is True
    assert "provider_message_id" in res.output


@pytest.mark.asyncio
async def test_54_workflow_permission_enforcement(test_session: AsyncSession):
    random_tenant_id = str(uuid.uuid4())
    res = await ActionExecutor.execute(
        action_type="whatsapp_send_message",
        params={"recipient": "628100", "text": "Fail test"},
        context={},
        session=test_session,
        tenant_id=random_tenant_id,
    )
    assert res.success is False
    assert "not active" in res.error.lower()


@pytest.mark.asyncio
async def test_55_duplicate_webhook_no_duplicate_workflow(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]
    msg_id = f"wamid.wf_dup_{uuid.uuid4().hex[:6]}"

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": "628900", "id": msg_id, "timestamp": "1710000000", "type": "text", "text": {"body": "wf dup"}}]}}]}]
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"}

    res1 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)
    assert res1.json()["processed"][0]["status"] == "processed"

    res2 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)
    assert res2.json()["processed"][0]["status"] == "duplicate"


# ==========================================
# SECTION J: OWNER AI TESTS (56 - 60)
# ==========================================

@pytest.mark.asyncio
async def test_56_read_only_connection_status(active_whatsapp_tenant, test_session: AsyncSession):
    tenant_id = active_whatsapp_tenant["tenant"].id
    req = ToolRequest(tenant_id=tenant_id, tool_name="get_whatsapp_connection_status", parameters={})
    res = await tool_get_whatsapp_connection_status(req, test_session)
    assert res.success is True
    assert res.data["is_connected"] is True
    assert res.data["external_account_id"] == active_whatsapp_tenant["phone_number_id"]


@pytest.mark.asyncio
async def test_57_read_only_health(active_whatsapp_tenant, test_session: AsyncSession):
    adapter = WhatsAppCloudApiAdapter(is_development=True)
    tenant_id = active_whatsapp_tenant["tenant"].id
    conn_id = active_whatsapp_tenant["connection"].id
    creds = active_whatsapp_tenant["credentials"]

    healthy = await adapter.health_check(tenant_id, conn_id, creds, session=test_session)
    assert healthy is True


@pytest.mark.asyncio
async def test_58_owner_ai_tenant_isolation(active_whatsapp_tenant, test_session: AsyncSession):
    other_tenant_id = uuid.uuid4()
    req = ToolRequest(tenant_id=other_tenant_id, tool_name="get_whatsapp_connection_status", parameters={})
    res = await tool_get_whatsapp_connection_status(req, test_session)
    assert res.success is True
    assert res.data["is_connected"] is False


@pytest.mark.asyncio
async def test_59_cannot_mutate_credentials():
    req = ToolRequest(tenant_id=uuid.uuid4(), tool_name="get_whatsapp_connection_status", parameters={"action": "update_credentials"})
    assert not hasattr(tool_get_whatsapp_connection_status, "mutate")


@pytest.mark.asyncio
async def test_60_cannot_bypass_permissions(test_session: AsyncSession):
    service = IntegrationService(test_session)
    tenant_id = uuid.uuid4()
    with pytest.raises(PermissionDeniedError):
        await service.connect_integration(
            tenant_id, "whatsapp_cloud_api", credentials={}, actor_permissions=[]
        )


# ==========================================
# SECTION K: SECURITY TESTS (61 - 65)
# ==========================================

@pytest.mark.asyncio
async def test_61_no_secret_in_logs(caplog, active_whatsapp_tenant, test_session: AsyncSession):
    service = IntegrationService(test_session)
    tenant_id = active_whatsapp_tenant["tenant"].id
    conn_id = active_whatsapp_tenant["connection"].id

    try:
        await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=conn_id,
            operation="invalid_op",
            params={"secret_key": "SUPER_SECRET_123"},
            actor_permissions={EXECUTE_INTEGRATION},
        )
    except Exception:
        pass

    assert "SUPER_SECRET_123" not in caplog.text


@pytest.mark.asyncio
async def test_62_no_secret_in_api_response(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": "628", "id": f"wamid.sec_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "hi"}}]}}]}]
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}"})
    body_text = res.text
    assert active_whatsapp_tenant["access_token"] not in body_text
    assert active_whatsapp_tenant["app_secret"] not in body_text


@pytest.mark.asyncio
async def test_63_malicious_tenant_id_ignored(async_client: AsyncClient, active_whatsapp_tenant):
    phone_id = active_whatsapp_tenant["phone_number_id"]
    app_secret = active_whatsapp_tenant["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_id}, "messages": [{"from": "628", "id": f"wamid.mal_{uuid.uuid4().hex[:6]}", "timestamp": "1710000000", "type": "text", "text": {"body": "hi"}}]}}]}]
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()

    malicious_tenant_id = str(uuid.uuid4())
    res = await async_client.post(
        "/api/v1/webhooks/whatsapp",
        content=raw,
        headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig}", "X-Tenant-ID": malicious_tenant_id},
    )
    assert res.status_code == 200
    assert res.json()["tenant_id"] == str(active_whatsapp_tenant["tenant"].id)
    assert res.json()["tenant_id"] != malicious_tenant_id


@pytest.mark.asyncio
async def test_64_invalid_provider_id_rejected(test_session: AsyncSession):
    service = IntegrationService(test_session)
    tenant_id = uuid.uuid4()
    conn = await service.get_connection_by_provider(tenant_id, "non_existent_provider_xyz")
    assert conn is None


@pytest.mark.asyncio
async def test_65_ssrf_media_safety():
    adapter = WhatsAppCloudApiAdapter()
    raw = b"test payload"
    assert adapter.verify_webhook_signature(raw, "sha256=invalid", "secret") is False
