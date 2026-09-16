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
    c1, created1 = await repo.get_or_create(tenant.id, "081299998888", name="Concurrency User")
    c2, created2 = await repo.get_or_create(tenant.id, "+6281299998888", name="Concurrency User Alias")

    assert c1.id == c2.id
    assert c1.phone == "6281299998888"
    assert created1 is True
    assert created2 is False


@pytest.mark.asyncio
async def test_r3_conversation_get_or_create_concurrency(db_session: AsyncSession):
    tenant = Tenant(name="Conv Tenant", slug=f"cvt-{uuid.uuid4().hex[:6]}", is_active=True)
    db_session.add(tenant)
    await db_session.commit()

    c_repo = CustomerRepository(db_session)
    cust, _ = await c_repo.get_or_create(tenant.id, "081277776666", name="Conv User")

    conv_repo = ConversationRepository(db_session)
    cv1, created1 = await conv_repo.get_or_create_active(tenant.id, cust.id, channel="whatsapp")
    cv2, created2 = await conv_repo.get_or_create_active(tenant.id, cust.id, channel="whatsapp")

    assert cv1.id == cv2.id
    assert cv1.status == "OPEN"
    assert created1 is True
    assert created2 is False


@pytest.mark.asyncio
async def test_r3_message_status_state_machine(db_session: AsyncSession):
    from app.core.messaging_state import validate_message_status_transition, InvalidStateTransitionError

    tenant = Tenant(name="Msg Tenant", slug=f"mt-{uuid.uuid4().hex[:6]}", is_active=True)
    db_session.add(tenant)
    await db_session.commit()

    cust, _ = await CustomerRepository(db_session).get_or_create(tenant.id, "081255554444")
    conv, _ = await ConversationRepository(db_session).get_or_create_active(tenant.id, cust.id)

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
