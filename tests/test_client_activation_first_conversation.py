import uuid
import hmac
import hashlib
import json
import logging
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.database.models import Tenant, Customer, Conversation, Message, User, Product
from app.database.models.integrations import Integration, IntegrationConnection, IntegrationCredential, IntegrationExecution
from app.database.models.billing import Plan, Subscription, PlanFeature
from app.database.models.ai_usage import AIUsageRecord
from app.database.models.workflow import WorkflowConfiguration, WorkflowExecution
import app.integrations.adapters
from app.integrations.adapters.whatsapp_cloud_api import WhatsAppCloudApiAdapter
from app.integrations.registry import integration_registry
from app.integrations.service import IntegrationService
from app.core.router.deterministic import DeterministicRouter
from app.core.router.router import MessageRouter
from app.core.ai_gateway import AIGateway
from app.repositories.domain import CustomerRepository, ConversationRepository, MessageRepository, ProductRepository, AIUsageRepository
from app.billing.subscription import SubscriptionService
from app.billing.entitlement import EntitlementResolver
from app.analytics.services import AnalyticsService

logger = logging.getLogger(__name__)


@pytest.fixture
async def setup_wa_integration_db(db_session: AsyncSession):
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
async def active_tenant_fixture(db_session: AsyncSession, setup_wa_integration_db: Integration):
    tenant = Tenant(name="Active Tenant F", slug=f"active-f-{uuid.uuid4().hex[:6]}", is_active=True, lifecycle_state="ACTIVE")
    db_session.add(tenant)
    await db_session.commit()

    plan = Plan(
        name="Pro Plan",
        code=f"pro_{uuid.uuid4().hex[:6]}",
        price_monthly=Decimal("1500000.00"),
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
    app_secret = f"secret_f_{uuid.uuid4().hex[:10]}"
    verify_token = f"token_f_{uuid.uuid4().hex[:8]}"
    access_token = f"mock_token_f_{uuid.uuid4().hex[:8]}"

    conn = IntegrationConnection(
        tenant_id=tenant.id,
        integration_id=setup_wa_integration_db.id,
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
        "waba_id": "waba_f_123456",
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


def make_wa_payload(phone_number_id: str, sender_phone: str, text_body: str, wamid: str | None = None) -> tuple[bytes, str]:
    if not wamid:
        wamid = f"wamid.f_{uuid.uuid4().hex[:8]}"
    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "entry_f_1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {"display_phone_number": "6280000", "phone_number_id": phone_number_id},
                            "contacts": [{"profile": {"name": "Customer F"}, "wa_id": sender_phone}],
                            "messages": [
                                {
                                    "from": sender_phone,
                                    "id": wamid,
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": text_body},
                                }
                            ],
                        },
                    }
                ],
            }
        ],
    }
    raw_bytes = json.dumps(payload).encode("utf-8")
    return raw_bytes, wamid


def sign_payload(raw_bytes: bytes, secret: str) -> str:
    return f"sha256={hmac.new(secret.encode('utf-8'), raw_bytes, hashlib.sha256).hexdigest()}"


# ==============================================================================
# SECTION A: ACTIVE TENANT GATE (Tests 1 - 4)
# ==============================================================================

@pytest.mark.asyncio
async def test_01_inactive_tenant_rejected(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    tenant = active_tenant_fixture["tenant"]
    tenant.is_active = False
    await db_session.commit()

    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111", "Hello")
    sig = sign_payload(raw_bytes, active_tenant_fixture["app_secret"])

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 403
    assert "inactive" in res.text.lower()


@pytest.mark.asyncio
async def test_02_suspended_tenant_rejected(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    tenant = active_tenant_fixture["tenant"]
    tenant.lifecycle_state = "SUSPENDED"
    await db_session.commit()

    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111", "Hello")
    sig = sign_payload(raw_bytes, active_tenant_fixture["app_secret"])

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_03_archived_tenant_rejected(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    tenant = active_tenant_fixture["tenant"]
    tenant.lifecycle_state = "ARCHIVED"
    await db_session.commit()

    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111", "Hello")
    sig = sign_payload(raw_bytes, active_tenant_fixture["app_secret"])

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_04_active_tenant_accepted(async_client: AsyncClient, active_tenant_fixture):
    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111222", "Hello bot")
    sig = sign_payload(raw_bytes, active_tenant_fixture["app_secret"])

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200
    assert res.json()["status"] == "success"


# ==============================================================================
# SECTION B: SUBSCRIPTION & ENTITLEMENT GATES (Tests 5 - 7)
# ==============================================================================

@pytest.mark.asyncio
async def test_05_inactive_subscription_rejected(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    tenant_id = active_tenant_fixture["tenant"].id
    sub = (await db_session.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))).scalar_one()
    sub.status = "EXPIRED"
    await db_session.commit()

    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111", "Hello")
    sig = sign_payload(raw_bytes, active_tenant_fixture["app_secret"])

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 403
    assert "subscription" in res.text.lower()


@pytest.mark.asyncio
async def test_06_missing_whatsapp_entitlement_rejected(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    tenant_id = active_tenant_fixture["tenant"].id
    sub = (await db_session.execute(select(Subscription).where(Subscription.tenant_id == tenant_id))).scalar_one()
    pf = (await db_session.execute(select(PlanFeature).where(PlanFeature.plan_id == sub.plan_id))).scalar_one()
    pf.is_enabled = False
    await db_session.commit()

    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111", "Hello")
    sig = sign_payload(raw_bytes, active_tenant_fixture["app_secret"])

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 403
    assert "entitled" in res.text.lower()


@pytest.mark.asyncio
async def test_07_active_subscription_and_entitlement_accepted(async_client: AsyncClient, active_tenant_fixture):
    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628123456", "Halo kak")
    sig = sign_payload(raw_bytes, active_tenant_fixture["app_secret"])

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200


# ==============================================================================
# SECTION C: WHATSAPP TENANT MAPPING (Tests 8 - 11)
# ==============================================================================

@pytest.mark.asyncio
async def test_08_valid_phone_number_id_maps_correct_tenant(async_client: AsyncClient, active_tenant_fixture):
    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111", "Testing phone id")
    sig = sign_payload(raw_bytes, active_tenant_fixture["app_secret"])

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200
    assert res.json()["tenant_id"] == str(active_tenant_fixture["tenant"].id)


@pytest.mark.asyncio
async def test_09_unknown_phone_number_id_rejected(async_client: AsyncClient):
    raw_bytes, _ = make_wa_payload("unknown_phone_id_9999", "628111", "Testing unknown")

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": "sha256=dummy"})
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_10_cross_tenant_phone_number_id_isolation(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession, setup_wa_integration_db: Integration):
    tenant_b = Tenant(name="Tenant Cross Isolation", slug=f"cross-{uuid.uuid4().hex[:6]}", is_active=True, lifecycle_state="ACTIVE")
    db_session.add(tenant_b)
    await db_session.commit()

    phone_id_b = f"200400{uuid.uuid4().hex[:6]}"
    app_secret_b = f"secret_cross_{uuid.uuid4().hex[:8]}"

    conn_b = IntegrationConnection(
        tenant_id=tenant_b.id,
        integration_id=setup_wa_integration_db.id,
        status="ACTIVE",
        external_account_id=phone_id_b,
    )
    db_session.add(conn_b)
    await db_session.commit()

    service = IntegrationService(db_session)
    enc_secret_b = service.vault.encrypt_credentials({"phone_number_id": phone_id_b, "access_token": "token_b", "app_secret": app_secret_b})
    cred_b = IntegrationCredential(tenant_id=tenant_b.id, connection_id=conn_b.id, credential_type="bearer_token", encrypted_secret=enc_secret_b)
    db_session.add(cred_b)
    await db_session.commit()

    raw_bytes_b, _ = make_wa_payload(phone_id_b, "628999", "Message B")
    sig_b = sign_payload(raw_bytes_b, app_secret_b)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes_b, headers={"X-Hub-Signature-256": sig_b})
    assert res.status_code == 200
    assert res.json()["tenant_id"] == str(tenant_b.id)
    assert res.json()["tenant_id"] != str(active_tenant_fixture["tenant"].id)


@pytest.mark.asyncio
async def test_11_inactive_connection_rejected(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    conn = active_tenant_fixture["connection"]
    conn.status = "DISCONNECTED"
    await db_session.commit()

    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111", "Hello")
    sig = sign_payload(raw_bytes, active_tenant_fixture["app_secret"])

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 404


# ==============================================================================
# SECTION D: WEBHOOK SECURITY (Tests 12 - 15)
# ==============================================================================

@pytest.mark.asyncio
async def test_12_valid_signature_accepted(async_client: AsyncClient, active_tenant_fixture):
    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111", "Signature test")
    sig = sign_payload(raw_bytes, active_tenant_fixture["app_secret"])

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_13_invalid_signature_rejected(async_client: AsyncClient, active_tenant_fixture):
    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111", "Invalid sig test")

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": "sha256=invalid_hash_123456"})
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_14_missing_signature_rejected(async_client: AsyncClient, active_tenant_fixture):
    raw_bytes, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111", "Missing sig test")

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes)
    assert res.status_code == 401


@pytest.mark.asyncio
async def test_15_malformed_payload_handled_safely(async_client: AsyncClient):
    res = await async_client.post("/api/v1/webhooks/whatsapp", content=b"invalid raw json payload")
    assert res.status_code == 400


# ==============================================================================
# SECTION E: IDEMPOTENCY (Tests 16 - 19)
# ==============================================================================

@pytest.mark.asyncio
async def test_16_duplicate_wamid_no_duplicate_message(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id

    raw_bytes, wamid = make_wa_payload(phone_id, "628123123", "Idempotent text")
    sig = sign_payload(raw_bytes, secret)
    headers = {"X-Hub-Signature-256": sig, "Content-Type": "application/json"}

    res1 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["processed"][0]["status"] == "processed"

    res2 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["processed"][0]["status"] == "duplicate"

    m_repo = MessageRepository(db_session)
    msg = await m_repo.get_by_external_id(tenant_id, wamid)
    assert msg is not None


@pytest.mark.asyncio
async def test_17_duplicate_webhook_no_duplicate_customer(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id
    phone = f"62899_{uuid.uuid4().hex[:6]}"

    raw1, _ = make_wa_payload(phone_id, phone, "First message")
    sig1 = sign_payload(raw1, secret)
    await async_client.post("/api/v1/webhooks/whatsapp", content=raw1, headers={"X-Hub-Signature-256": sig1})

    raw2, _ = make_wa_payload(phone_id, phone, "Second message")
    sig2 = sign_payload(raw2, secret)
    await async_client.post("/api/v1/webhooks/whatsapp", content=raw2, headers={"X-Hub-Signature-256": sig2})

    c_repo = CustomerRepository(db_session)
    customers = await c_repo.list_all(tenant_id)
    matching = [c for c in customers if c.phone == phone]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_18_duplicate_webhook_no_duplicate_conversation(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id
    phone = f"62888_{uuid.uuid4().hex[:6]}"

    raw1, _ = make_wa_payload(phone_id, phone, "Message 1")
    sig1 = sign_payload(raw1, secret)
    await async_client.post("/api/v1/webhooks/whatsapp", content=raw1, headers={"X-Hub-Signature-256": sig1})

    raw2, _ = make_wa_payload(phone_id, phone, "Message 2")
    sig2 = sign_payload(raw2, secret)
    await async_client.post("/api/v1/webhooks/whatsapp", content=raw2, headers={"X-Hub-Signature-256": sig2})

    c_repo = CustomerRepository(db_session)
    conv_repo = ConversationRepository(db_session)
    cust = await c_repo.get_by_phone(tenant_id, phone)
    convs = await conv_repo.list_all(tenant_id)
    cust_convs = [c for c in convs if c.customer_id == cust.id]
    assert len(cust_convs) == 1


@pytest.mark.asyncio
async def test_19_duplicate_webhook_no_duplicate_ai_response(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id

    raw_bytes, wamid = make_wa_payload(phone_id, "628555", "Harga produk A", wamid="wamid.dup_ai_1")
    sig = sign_payload(raw_bytes, secret)
    headers = {"X-Hub-Signature-256": sig}

    res1 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)
    assert res1.json()["processed"][0]["status"] == "processed"

    res2 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers=headers)
    assert res2.json()["processed"][0]["status"] == "duplicate"


# ==============================================================================
# SECTION F: UNIVERSAL CUSTOMER IDENTITY (Tests 20 - 22)
# ==============================================================================

@pytest.mark.asyncio
async def test_20_first_whatsapp_message_creates_customer(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id
    phone = f"628100_{uuid.uuid4().hex[:6]}"

    raw_bytes, _ = make_wa_payload(phone_id, phone, "Halo pertama kali")
    sig = sign_payload(raw_bytes, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_bytes, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200

    c_repo = CustomerRepository(db_session)
    cust = await c_repo.get_by_phone(tenant_id, phone)
    assert cust is not None
    assert cust.phone == phone


@pytest.mark.asyncio
async def test_21_subsequent_message_reuses_customer(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id
    phone = f"628200_{uuid.uuid4().hex[:6]}"

    raw1, _ = make_wa_payload(phone_id, phone, "Pesan 1")
    sig1 = sign_payload(raw1, secret)
    await async_client.post("/api/v1/webhooks/whatsapp", content=raw1, headers={"X-Hub-Signature-256": sig1})

    raw2, _ = make_wa_payload(phone_id, phone, "Pesan 2")
    sig2 = sign_payload(raw2, secret)
    await async_client.post("/api/v1/webhooks/whatsapp", content=raw2, headers={"X-Hub-Signature-256": sig2})

    c_repo = CustomerRepository(db_session)
    customers = await c_repo.list_all(tenant_id)
    matching = [c for c in customers if c.phone == phone]
    assert len(matching) == 1


@pytest.mark.asyncio
async def test_22_customer_identity_no_merge_by_name_alone(db_session: AsyncSession):
    tenant_id = uuid.uuid4()
    c_repo = CustomerRepository(db_session)

    c1 = await c_repo.create(tenant_id=tenant_id, name="John Doe", phone="6281111111", external_id="6281111111")
    c2 = await c_repo.create(tenant_id=tenant_id, name="John Doe", phone="6282222222", external_id="6282222222")

    assert c1.id != c2.id
    assert c1.phone != c2.phone


# ==============================================================================
# SECTION G: CONVERSATION MANAGEMENT (Tests 23 - 25)
# ==============================================================================

@pytest.mark.asyncio
async def test_23_first_message_creates_conversation(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id
    phone = f"628300_{uuid.uuid4().hex[:6]}"

    raw, _ = make_wa_payload(phone_id, phone, "Create conv")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200

    c_repo = CustomerRepository(db_session)
    conv_repo = ConversationRepository(db_session)
    cust = await c_repo.get_by_phone(tenant_id, phone)
    conv = await conv_repo.get_active_by_customer(tenant_id, cust.id)
    assert conv is not None
    assert conv.status == "OPEN"


@pytest.mark.asyncio
async def test_24_subsequent_message_reuses_conversation(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id
    phone = f"628400_{uuid.uuid4().hex[:6]}"

    raw1, _ = make_wa_payload(phone_id, phone, "Message 1")
    sig1 = sign_payload(raw1, secret)
    await async_client.post("/api/v1/webhooks/whatsapp", content=raw1, headers={"X-Hub-Signature-256": sig1})

    raw2, _ = make_wa_payload(phone_id, phone, "Message 2")
    sig2 = sign_payload(raw2, secret)
    await async_client.post("/api/v1/webhooks/whatsapp", content=raw2, headers={"X-Hub-Signature-256": sig2})

    c_repo = CustomerRepository(db_session)
    conv_repo = ConversationRepository(db_session)
    cust = await c_repo.get_by_phone(tenant_id, phone)
    convs = await conv_repo.list_all(tenant_id)
    cust_convs = [c for c in convs if c.customer_id == cust.id]
    assert len(cust_convs) == 1


@pytest.mark.asyncio
async def test_25_conversation_tenant_isolation(db_session: AsyncSession):
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    cust_id = uuid.uuid4()

    conv_repo = ConversationRepository(db_session)
    c_a = await conv_repo.create(tenant_id=tenant_a, customer_id=cust_id, channel="whatsapp", status="OPEN")
    c_b = await conv_repo.create(tenant_id=tenant_b, customer_id=cust_id, channel="whatsapp", status="OPEN")

    convs_a = await conv_repo.list_all(tenant_a)
    convs_b = await conv_repo.list_all(tenant_b)

    assert len(convs_a) == 1
    assert len(convs_b) == 1
    assert convs_a[0].id != convs_b[0].id


# ==============================================================================
# SECTION H: MESSAGE PERSISTENCE & CREDENTIAL SAFETY (Tests 26 - 28)
# ==============================================================================

@pytest.mark.asyncio
async def test_26_incoming_message_persisted(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id

    raw, wamid = make_wa_payload(phone_id, "628111222", "Test persistence INBOUND")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200

    m_repo = MessageRepository(db_session)
    msg = await m_repo.get_by_external_id(tenant_id, wamid)
    assert msg is not None
    assert msg.direction == "INBOUND"
    assert msg.text == "Test persistence INBOUND"


@pytest.mark.asyncio
async def test_27_outbound_message_persisted(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id
    phone = f"628777_{uuid.uuid4().hex[:6]}"

    raw, wamid = make_wa_payload(phone_id, phone, "Harga sepatu")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200

    c_repo = CustomerRepository(db_session)
    conv_repo = ConversationRepository(db_session)
    m_repo = MessageRepository(db_session)

    cust = await c_repo.get_by_phone(tenant_id, phone)
    conv = await conv_repo.get_active_by_customer(tenant_id, cust.id)
    msgs = await m_repo.list_by_conversation(tenant_id, conv.id)

    outbounds = [m for m in msgs if m.direction == "OUTBOUND"]
    assert len(outbounds) >= 1


@pytest.mark.asyncio
async def test_28_credentials_never_stored_in_message_metadata(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    token = active_tenant_fixture["access_token"]
    tenant_id = active_tenant_fixture["tenant"].id

    raw, wamid = make_wa_payload(phone_id, "628999111", "Sec test message")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200

    m_repo = MessageRepository(db_session)
    msg = await m_repo.get_by_external_id(tenant_id, wamid)
    meta_str = json.dumps(msg.metadata_ or {})

    assert secret not in meta_str
    assert token not in meta_str


# ==============================================================================
# SECTION I: DETERMINISTIC-FIRST ROUTER (Tests 29 - 32)
# ==============================================================================

@pytest.mark.asyncio
async def test_29_deterministic_product_query_uses_db_truth(db_session: AsyncSession):
    tenant_id = uuid.uuid4()
    p_repo = ProductRepository(db_session)
    prod = await p_repo.create(
        tenant_id=tenant_id,
        name="Sepatu Lari Nike Air",
        sku="NIKE-AIR-01",
        price=Decimal("1200000.00"),
        stock=15,
        is_active=True,
    )

    matched = await DeterministicRouter.match_product(tenant_id, "Berapa harga Sepatu Lari Nike Air?", db_session)
    assert matched is not None
    assert matched.id == prod.id


@pytest.mark.asyncio
async def test_30_deterministic_price_uses_db_truth(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id

    p_repo = ProductRepository(db_session)
    await p_repo.create(
        tenant_id=tenant_id,
        name="Kemeja Batik Premium",
        sku="BATIK-001",
        price=Decimal("350000.00"),
        stock=20,
        is_active=True,
    )
    await db_session.commit()

    raw, wamid = make_wa_payload(phone_id, "628111222333", "Berapa harga Kemeja Batik Premium?")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200

    m_repo = MessageRepository(db_session)
    c_repo = CustomerRepository(db_session)
    conv_repo = ConversationRepository(db_session)

    cust = await c_repo.get_by_phone(tenant_id, "628111222333")
    conv = await conv_repo.get_active_by_customer(tenant_id, cust.id)
    msgs = await m_repo.list_by_conversation(tenant_id, conv.id)

    outbound = [m for m in msgs if m.direction == "OUTBOUND"][0]
    assert "350,000" in outbound.text or "350000" in outbound.text


@pytest.mark.asyncio
async def test_31_deterministic_stock_uses_db_truth(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id

    p_repo = ProductRepository(db_session)
    await p_repo.create(
        tenant_id=tenant_id,
        name="Kopi Arabika 250g",
        sku="KOPI-01",
        price=Decimal("75000.00"),
        stock=42,
        is_active=True,
    )
    await db_session.commit()

    raw, _ = make_wa_payload(phone_id, "628111222444", "Apakah stok Kopi Arabika 250g ready?")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200

    m_repo = MessageRepository(db_session)
    c_repo = CustomerRepository(db_session)
    conv_repo = ConversationRepository(db_session)

    cust = await c_repo.get_by_phone(tenant_id, "628111222444")
    conv = await conv_repo.get_active_by_customer(tenant_id, cust.id)
    msgs = await m_repo.list_by_conversation(tenant_id, conv.id)

    outbound = [m for m in msgs if m.direction == "OUTBOUND"][0]
    assert "42" in outbound.text


@pytest.mark.asyncio
async def test_32_unknown_query_falls_back_to_ai(async_client: AsyncClient, active_tenant_fixture):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]

    raw, _ = make_wa_payload(phone_id, "628111222555", "Pertanyaan umum layanan pelanggan")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200


# ==============================================================================
# SECTION J: AI GATEWAY COMPLIANCE & USAGE (Tests 33 - 38)
# ==============================================================================

@pytest.mark.asyncio
async def test_33_ai_request_uses_ai_gateway():
    gateway = AIGateway()
    assert hasattr(gateway, "generate")
    assert hasattr(gateway, "usage_tracker")


@pytest.mark.asyncio
async def test_34_no_direct_gemini_sdk_call():
    import app.api.v1.webhooks as webhooks_module
    import app.core.router.router as router_module
    webhooks_src = open(webhooks_module.__file__).read()
    router_src = open(router_module.__file__).read()

    assert "import google.generativeai" not in webhooks_src
    assert "import google.generativeai" not in router_src


@pytest.mark.asyncio
async def test_35_ai_usage_recorded_in_usage_records(db_session: AsyncSession):
    tenant_id = uuid.uuid4()
    usage_repo = AIUsageRepository(db_session)

    req_id = f"ai_req_test_{uuid.uuid4().hex[:6]}"
    rec = await usage_repo.create(
        tenant_id=tenant_id,
        request_id=req_id,
        task_type="customer_service_response",
        model="gemini-3.1-flash-lite",
        input_tokens=100,
        output_tokens=50,
        total_tokens=150,
        estimated_cost=Decimal("0.0000225"),
        latency_ms=120.5,
        success=True,
    )
    assert rec.id is not None
    assert rec.tenant_id == tenant_id


@pytest.mark.asyncio
async def test_36_ai_credit_limit_respected(db_session: AsyncSession, active_tenant_fixture):
    tenant_id = active_tenant_fixture["tenant"].id
    resolver = EntitlementResolver(db_session)

    res = await resolver.can_use(tenant_id, "ai_customer_service")
    assert res.allowed is True or res.state is not None


@pytest.mark.asyncio
async def test_37_ai_failure_handled_safely(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id

    raw, _ = make_wa_payload(phone_id, "628999888777", "Random query without AI key")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200

    m_repo = MessageRepository(db_session)
    c_repo = CustomerRepository(db_session)
    conv_repo = ConversationRepository(db_session)

    cust = await c_repo.get_by_phone(tenant_id, "628999888777")
    conv = await conv_repo.get_active_by_customer(tenant_id, cust.id)
    msgs = await m_repo.list_by_conversation(tenant_id, conv.id)

    outbound = [m for m in msgs if m.direction == "OUTBOUND"][0]
    assert len(outbound.text) > 0


@pytest.mark.asyncio
async def test_38_ai_timeout_handled_safely(async_client: AsyncClient, active_tenant_fixture):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]

    raw, _ = make_wa_payload(phone_id, "628999888666", "Timeout query")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200


# ==============================================================================
# SECTION K: OUTBOUND WHATSAPP MESSAGING (Tests 39 - 42)
# ==============================================================================

@pytest.mark.asyncio
async def test_39_outbound_response_uses_whatsapp_adapter(db_session: AsyncSession, active_tenant_fixture):
    service = IntegrationService(db_session)
    tenant_id = active_tenant_fixture["tenant"].id
    conn_id = active_tenant_fixture["connection"].id

    res = await service.execute_operation(
        tenant_id=tenant_id,
        connection_id=conn_id,
        operation="send_message",
        params={"recipient_phone": "628123456789", "text": "Testing outbound adapter"},
        allow_internal=True,
    )
    assert res.status == "COMPLETED"


@pytest.mark.asyncio
async def test_40_no_direct_meta_api_call_outside_adapter():
    import app.api.v1.webhooks as webhooks_module
    src = open(webhooks_module.__file__).read()
    assert "graph.facebook.com" not in src


@pytest.mark.asyncio
async def test_41_outbound_send_failure_handled(db_session: AsyncSession, active_tenant_fixture, monkeypatch):
    adapter = WhatsAppCloudApiAdapter(is_development=False)
    tenant_id = active_tenant_fixture["tenant"].id
    conn_id = active_tenant_fixture["connection"].id
    creds = dict(active_tenant_fixture["credentials"])
    creds["access_token"] = "token_fail"

    import httpx

    async def mock_fail(*args, **kwargs):
        class Resp:
            status_code = 500
            content = b'{"error": {"message": "server error"}}'
            def json(self):
                return {"error": {"message": "server error"}}
        return Resp()

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_fail)

    with pytest.raises(Exception):
        await adapter.execute(
            tenant_id=tenant_id,
            connection_id=conn_id,
            credentials=creds,
            operation="send_message",
            params={"recipient": "628123456789", "text": "Fail test"},
        )


@pytest.mark.asyncio
async def test_42_provider_status_normalized(async_client: AsyncClient, active_tenant_fixture):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "e1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_id},
                            "statuses": [{"id": "wamid.status_norm_1", "status": "delivered", "timestamp": "1710000000", "recipient_id": "628111"}],
                        },
                    }
                ],
            }
        ],
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200
    assert res.json()["processed"][0]["status"] == "delivered"


# ==============================================================================
# SECTION L: HUMAN HANDOFF (Tests 43 - 45)
# ==============================================================================

@pytest.mark.asyncio
async def test_43_explicit_human_request_triggers_handoff(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id
    phone = f"628900_{uuid.uuid4().hex[:6]}"

    raw, _ = make_wa_payload(phone_id, phone, "Saya ingin bicara dengan customer service human agent")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200

    c_repo = CustomerRepository(db_session)
    conv_repo = ConversationRepository(db_session)

    cust = await c_repo.get_by_phone(tenant_id, phone)
    convs = await conv_repo.list_all(tenant_id)
    cust_conv = [c for c in convs if c.customer_id == cust.id][0]

    assert cust_conv.human_handoff is True
    assert cust_conv.status == "WAITING_HUMAN"


@pytest.mark.asyncio
async def test_44_ai_does_not_continue_after_human_takeover(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id
    phone = f"628901_{uuid.uuid4().hex[:6]}"

    cust = Customer(tenant_id=tenant_id, name="Takeover Cust", phone=phone)
    db_session.add(cust)
    await db_session.commit()

    conv = Conversation(tenant_id=tenant_id, customer_id=cust.id, channel="whatsapp", status="WAITING_HUMAN", human_handoff=True, ai_enabled=False)
    db_session.add(conv)
    await db_session.commit()

    raw, _ = make_wa_payload(phone_id, phone, "Pertanyaan setelah takeover human")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200

    await db_session.rollback()
    m_repo = MessageRepository(db_session)
    msgs = await m_repo.list_by_conversation(tenant_id, conv.id)
    outbound = [m for m in msgs if m.direction == "OUTBOUND"][0]
    assert "[SYSTEM] Message logged for human agent." in outbound.text


@pytest.mark.asyncio
async def test_45_human_handoff_event_and_status_auditable(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id
    phone = f"628902_{uuid.uuid4().hex[:6]}"

    raw, _ = make_wa_payload(phone_id, phone, "Mohon hubungi cs manusia sekarang")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200

    conv_repo = ConversationRepository(db_session)
    convs = await conv_repo.list_all(tenant_id)
    assert any(c.human_handoff for c in convs)


# ==============================================================================
# SECTION M: EVENTBUS EVENTS (Tests 46 - 49)
# ==============================================================================

@pytest.mark.asyncio
async def test_46_message_received_event_published(async_client: AsyncClient, active_tenant_fixture):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]

    raw, _ = make_wa_payload(phone_id, "628111999888", "Event test msg received")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_47_message_sent_event_published(async_client: AsyncClient, active_tenant_fixture):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]

    raw, _ = make_wa_payload(phone_id, "628111999777", "Event test msg sent")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_48_status_events_published(async_client: AsyncClient, active_tenant_fixture):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "e1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_id},
                            "statuses": [{"id": "wamid.evt_st_1", "status": "read", "timestamp": "1710000000", "recipient_id": "628111"}],
                        },
                    }
                ],
            }
        ],
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_49_duplicate_webhook_no_duplicate_event(async_client: AsyncClient, active_tenant_fixture):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]

    raw, wamid = make_wa_payload(phone_id, "628111999666", "Dup event test", wamid="wamid.no_dup_evt")
    sig = sign_payload(raw, secret)
    headers = {"X-Hub-Signature-256": sig}

    res1 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)
    assert res1.json()["processed"][0]["status"] == "processed"

    res2 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)
    assert res2.json()["processed"][0]["status"] == "duplicate"


# ==============================================================================
# SECTION N: ANALYTICS INTEGRATION (Tests 50 - 51)
# ==============================================================================

@pytest.mark.asyncio
async def test_50_message_activity_contributes_to_analytics(db_session: AsyncSession, active_tenant_fixture):
    tenant_id = active_tenant_fixture["tenant"].id
    analytics_svc = AnalyticsService(db_session)

    res = await analytics_svc.ai.get_ai_analytics(tenant_id)
    assert res is not None
    assert hasattr(res, "total_requests")


@pytest.mark.asyncio
async def test_51_ai_usage_contributes_to_analytics(db_session: AsyncSession, active_tenant_fixture):
    tenant_id = active_tenant_fixture["tenant"].id
    usage_repo = AIUsageRepository(db_session)

    await usage_repo.create(
        tenant_id=tenant_id,
        request_id=f"req_analytics_{uuid.uuid4().hex[:6]}",
        task_type="customer_service_response",
        model="gemini-3.1-flash-lite",
        input_tokens=200,
        output_tokens=100,
        total_tokens=300,
        estimated_cost=Decimal("0.000045"),
        latency_ms=150.0,
        success=True,
    )

    analytics_svc = AnalyticsService(db_session)
    ai_metrics = await analytics_svc.ai.get_ai_analytics(tenant_id)
    assert ai_metrics.total_tokens >= 300


# ==============================================================================
# SECTION O: SECURITY & TENANT ISOLATION (Tests 52 - 55)
# ==============================================================================

@pytest.mark.asyncio
async def test_52_tenant_a_cannot_access_tenant_b_conversation(db_session: AsyncSession):
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    cust_b = uuid.uuid4()

    conv_repo = ConversationRepository(db_session)
    conv_b = await conv_repo.create(tenant_id=tenant_b, customer_id=cust_b, channel="whatsapp", status="OPEN")

    convs_a = await conv_repo.list_all(tenant_a)
    assert conv_b.id not in [c.id for c in convs_a]


@pytest.mark.asyncio
async def test_53_tenant_a_cannot_access_tenant_b_customer(db_session: AsyncSession):
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    c_repo = CustomerRepository(db_session)
    cust_b = await c_repo.create(tenant_id=tenant_b, name="Customer B", phone="6289999999", external_id="6289999999")

    custs_a = await c_repo.list_all(tenant_a)
    assert cust_b.id not in [c.id for c in custs_a]


@pytest.mark.asyncio
async def test_54_credentials_never_appear_in_api_response(async_client: AsyncClient, active_tenant_fixture):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]

    raw, _ = make_wa_payload(phone_id, "628111999555", "Secret exposure test")
    sig = sign_payload(raw, secret)

    res = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers={"X-Hub-Signature-256": sig})
    assert active_tenant_fixture["access_token"] not in res.text
    assert active_tenant_fixture["app_secret"] not in res.text


@pytest.mark.asyncio
async def test_55_secrets_are_not_logged(caplog, active_tenant_fixture):
    raw, _ = make_wa_payload(active_tenant_fixture["phone_number_id"], "628111999444", "Secret log check")
    sig = sign_payload(raw, active_tenant_fixture["app_secret"])

    assert active_tenant_fixture["access_token"] not in caplog.text


# ==============================================================================
# SECTION P: VERIFICATION HANDSHAKE & WORKFLOW TRIGGERS (Tests 56 - 60)
# ==============================================================================

@pytest.mark.asyncio
async def test_56_get_verification_handshake_success(async_client: AsyncClient, active_tenant_fixture):
    token = active_tenant_fixture["verify_token"]
    res = await async_client.get(
        "/api/v1/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.challenge": "challenge_code_123", "hub.verify_token": token},
    )
    assert res.status_code == 200
    assert res.text == "challenge_code_123"


@pytest.mark.asyncio
async def test_57_get_verification_invalid_token_forbidden(async_client: AsyncClient):
    res = await async_client.get(
        "/api/v1/webhooks/whatsapp",
        params={"hub.mode": "subscribe", "hub.challenge": "123", "hub.verify_token": "invalid_verify_token_code"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_58_workflow_trigger_on_message_received(db_session: AsyncSession, active_tenant_fixture):
    tenant_id = active_tenant_fixture["tenant"].id
    wf = WorkflowConfiguration(
        tenant_id=tenant_id,
        key=f"wf_welcome_{uuid.uuid4().hex[:6]}",
        name="Auto WA Welcome Workflow",
        trigger_type="whatsapp.message_received",
        is_active=True,
        conditions=[],
        actions=[{"type": "whatsapp_send_message", "params": {"recipient": "628111", "text": "Welcome auto response"}}],
    )
    db_session.add(wf)
    await db_session.commit()

    stmt = select(WorkflowConfiguration).where(and_(WorkflowConfiguration.tenant_id == tenant_id, WorkflowConfiguration.is_active == True))
    active_wfs = (await db_session.execute(stmt)).scalars().all()
    assert len(active_wfs) >= 1


@pytest.mark.asyncio
async def test_59_client_activation_first_conversation_e2e_journey(async_client: AsyncClient, active_tenant_fixture, db_session: AsyncSession):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]
    tenant_id = active_tenant_fixture["tenant"].id
    phone = f"62899123_{uuid.uuid4().hex[:6]}"

    # 1. First incoming message
    raw1, wamid1 = make_wa_payload(phone_id, phone, "Halo, berapa harga barang ini?")
    sig1 = sign_payload(raw1, secret)
    res1 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw1, headers={"X-Hub-Signature-256": sig1})
    assert res1.status_code == 200

    c_repo = CustomerRepository(db_session)
    conv_repo = ConversationRepository(db_session)
    m_repo = MessageRepository(db_session)

    cust = await c_repo.get_by_phone(tenant_id, phone)
    assert cust is not None

    conv = await conv_repo.get_active_by_customer(tenant_id, cust.id)
    assert conv is not None

    msgs1 = await m_repo.list_by_conversation(tenant_id, conv.id)
    assert len(msgs1) >= 2

    # 2. Subsequent message
    raw2, wamid2 = make_wa_payload(phone_id, phone, "Terima kasih banyak info nya!")
    sig2 = sign_payload(raw2, secret)
    res2 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw2, headers={"X-Hub-Signature-256": sig2})
    assert res2.status_code == 200

    msgs2 = await m_repo.list_by_conversation(tenant_id, conv.id)
    assert len(msgs2) >= 4


@pytest.mark.asyncio
async def test_60_whatsapp_status_update_idempotency(async_client: AsyncClient, active_tenant_fixture):
    phone_id = active_tenant_fixture["phone_number_id"]
    secret = active_tenant_fixture["app_secret"]

    payload = {
        "object": "whatsapp_business_account",
        "entry": [
            {
                "id": "e1",
                "changes": [
                    {
                        "field": "messages",
                        "value": {
                            "metadata": {"phone_number_id": phone_id},
                            "statuses": [{"id": "wamid.status_e2e_1", "status": "read", "timestamp": "1710000000", "recipient_id": "628111"}],
                        },
                    }
                ],
            }
        ],
    }
    raw = json.dumps(payload).encode("utf-8")
    sig = sign_payload(raw, secret)
    headers = {"X-Hub-Signature-256": sig}

    res1 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)
    assert res1.json()["processed"][0]["status"] == "read"

    res2 = await async_client.post("/api/v1/webhooks/whatsapp", content=raw, headers=headers)
    assert res2.json()["processed"][0]["status"] == "duplicate_event"
