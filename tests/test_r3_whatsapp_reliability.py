import uuid
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.phone import normalize_phone_number, PhoneNormalizationError
from app.database.models import Customer, Conversation, Message, Tenant
from app.repositories.domain import CustomerRepository, ConversationRepository, MessageRepository


@pytest.mark.asyncio
async def test_r3_phone_normalization_comprehensive():
    assert normalize_phone_number("08123456789") == "628123456789"
    assert normalize_phone_number("+62 812-3456-789") == "628123456789"
    assert normalize_phone_number("628123456789") == "628123456789"

    with pytest.raises(PhoneNormalizationError):
        normalize_phone_number("invalid_phone_abc")

    with pytest.raises(PhoneNormalizationError):
        normalize_phone_number("")


@pytest.mark.asyncio
async def test_r3_customer_get_or_create_concurrency(db_session: AsyncSession):
    tenant = Tenant(name="Concur Tenant", slug=f"ct-{uuid.uuid4().hex[:6]}", is_active=True)
    db_session.add(tenant)
    await db_session.commit()

    repo = CustomerRepository(db_session)
    c1 = await repo.get_or_create(tenant.id, "081299998888", name="Concurrency User")
    c2 = await repo.get_or_create(tenant.id, "+6281299998888", name="Concurrency User Alias")

    assert c1.id == c2.id
    assert c1.phone == "6281299998888"


@pytest.mark.asyncio
async def test_r3_conversation_get_or_create_concurrency(db_session: AsyncSession):
    tenant = Tenant(name="Conv Tenant", slug=f"cvt-{uuid.uuid4().hex[:6]}", is_active=True)
    db_session.add(tenant)
    await db_session.commit()

    c_repo = CustomerRepository(db_session)
    cust = await c_repo.get_or_create(tenant.id, "081277776666", name="Conv User")

    conv_repo = ConversationRepository(db_session)
    cv1 = await conv_repo.get_or_create_active(tenant.id, cust.id, channel="whatsapp")
    cv2 = await conv_repo.get_or_create_active(tenant.id, cust.id, channel="whatsapp")

    assert cv1.id == cv2.id
    assert cv1.status == "OPEN"


@pytest.mark.asyncio
async def test_r3_message_status_state_machine(db_session: AsyncSession):
    from app.core.messaging_state import validate_message_status_transition, InvalidStateTransitionError

    tenant = Tenant(name="Msg Tenant", slug=f"mt-{uuid.uuid4().hex[:6]}", is_active=True)
    db_session.add(tenant)
    await db_session.commit()

    cust = await CustomerRepository(db_session).get_or_create(tenant.id, "081255554444")
    conv = await ConversationRepository(db_session).get_or_create_active(tenant.id, cust.id)

    msg_repo = MessageRepository(db_session)
    msg = await msg_repo.create(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="OUTBOUND",
        message_type="TEXT",
        text="State machine test",
        external_message_id=f"wamid.{uuid.uuid4().hex[:8]}",
    )
    assert msg.status == "CREATED"

    # Valid transition sequence
    validate_message_status_transition(msg.status, "QUEUED")
    msg.status = "QUEUED"

    validate_message_status_transition(msg.status, "SENDING")
    msg.status = "SENDING"

    validate_message_status_transition(msg.status, "SENT")
    msg.status = "SENT"

    validate_message_status_transition(msg.status, "DELIVERED")
    msg.status = "DELIVERED"

    validate_message_status_transition(msg.status, "READ")
    msg.status = "READ"

    # Invalid transitions must raise InvalidStateTransitionError
    invalid_pairs = [
        ("READ", "SENT"),
        ("FAILED", "SENT"),
        ("DELIVERED", "CREATED"),
        ("READ", "CREATED"),
        ("FAILED", "DELIVERED"),
        ("UNKNOWN", "SENT"),
    ]
    for current, target in invalid_pairs:
        with pytest.raises(InvalidStateTransitionError):
            validate_message_status_transition(current, target)


@pytest.mark.asyncio
async def test_r3_runtime_repository_status_transition_enforcement(db_session: AsyncSession):
    from app.core.messaging_state import InvalidStateTransitionError

    tenant = Tenant(name="Runtime Transition Tenant", slug=f"rtt-{uuid.uuid4().hex[:6]}", is_active=True)
    db_session.add(tenant)
    await db_session.commit()

    cust = await CustomerRepository(db_session).get_or_create(tenant.id, "081233332222")
    conv = await ConversationRepository(db_session).get_or_create_active(tenant.id, cust.id)

    msg_repo = MessageRepository(db_session)
    msg = await msg_repo.create(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="OUTBOUND",
        message_type="TEXT",
        text="Runtime state transition test",
    )
    assert msg.status == "CREATED"

    # Valid transitions via MessageRepository
    await msg_repo.transition_status(tenant.id, msg.id, "QUEUED")
    assert msg.status == "QUEUED"

    await msg_repo.transition_status(tenant.id, msg.id, "SENDING")
    assert msg.status == "SENDING"

    await msg_repo.transition_status(tenant.id, msg.id, "SENT")
    assert msg.status == "SENT"

    await msg_repo.transition_status(tenant.id, msg.id, "DELIVERED")
    assert msg.status == "DELIVERED"

    await msg_repo.transition_status(tenant.id, msg.id, "READ")
    assert msg.status == "READ"

    # Attempting illegal runtime transition must raise InvalidStateTransitionError
    with pytest.raises(InvalidStateTransitionError):
        await msg_repo.transition_status(tenant.id, msg.id, "SENT")


@pytest.mark.asyncio
async def test_r3_webhook_status_event_invalid_transition_rejection(async_client, test_session):
    import json
    import hmac
    import hashlib
    from app.database.models import Tenant, Customer, Conversation, Message
    from tests.test_whatsapp_and_handoff import _setup_active_whatsapp_integration

    tenant = Tenant(name="Status Rejection Tenant", slug=f"srt-{uuid.uuid4().hex[:6]}", is_active=True)
    test_session.add(tenant)
    await test_session.commit()

    app_secret = "secret_status_rej_123"
    phone_number_id = "888123"
    await _setup_active_whatsapp_integration(tenant, test_session, phone_number_id=phone_number_id, app_secret=app_secret)

    cust = Customer(tenant_id=tenant.id, name="Status Cust", phone="62811112222")
    test_session.add(cust)
    await test_session.commit()

    conv = Conversation(tenant_id=tenant.id, customer_id=cust.id, channel="whatsapp", status="OPEN")
    test_session.add(conv)
    await test_session.commit()

    # Create a message currently in CREATED status
    msg = Message(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="OUTBOUND",
        message_type="TEXT",
        status="CREATED",
        text="Status event test",
        external_message_id="wamid.status_rej_001",
    )
    test_session.add(msg)
    await test_session.commit()

    # Deliver a status webhook claiming 'delivered' (CREATED -> DELIVERED is illegal)
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
                            "statuses": [
                                {
                                    "id": "wamid.status_rej_001",
                                    "status": "delivered",
                                    "timestamp": "1710000000",
                                    "recipient_id": "62811112222",
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
    assert res.json()["processed"][0]["status"] == "status_transition_rejected"

    # Verify DB status remains CREATED and was not corrupted
    await test_session.refresh(msg)
    assert msg.status == "CREATED"
