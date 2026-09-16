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


@pytest.mark.asyncio
async def test_r3_outbound_webhook_path_success_and_events(async_client, test_session, monkeypatch):
    import json
    import hmac
    import hashlib
    from unittest.mock import AsyncMock
    from app.database.models import Tenant, Customer, Conversation, Message
    from app.integrations.schemas import OperationExecutionResult
    from app.integrations.service import IntegrationService
    from tests.test_whatsapp_and_handoff import _setup_active_whatsapp_integration

    tenant = Tenant(name="Outbound Success Tenant", slug=f"ost-{uuid.uuid4().hex[:6]}", is_active=True)
    test_session.add(tenant)
    await test_session.commit()

    app_secret = "secret_outbound_success_123"
    phone_number_id = "888333"
    await _setup_active_whatsapp_integration(tenant, test_session, phone_number_id=phone_number_id, app_secret=app_secret)

    provider_calls = 0

    async def mock_execute_op(*args, **kwargs):
        nonlocal provider_calls
        provider_calls += 1
        return OperationExecutionResult(
            execution_id=uuid.uuid4(),
            connection_id=uuid.uuid4(),
            operation="send_message",
            status="COMPLETED",
            result={"provider_message_id": "wamid.outbound_success_999"},
        )

    monkeypatch.setattr(IntegrationService, "execute_operation", mock_execute_op)

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
                                    "from": "62812345678",
                                    "id": f"wamid.inbound_{uuid.uuid4().hex[:6]}",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "Halo, tes outbound"},
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
    assert provider_calls == 1


@pytest.mark.asyncio
async def test_r3_outbound_webhook_path_timeout_unknown_no_retry(async_client, test_session, monkeypatch):
    import json
    import hmac
    import hashlib
    from app.database.models import Tenant, Message
    from app.integrations.service import IntegrationService
    from tests.test_whatsapp_and_handoff import _setup_active_whatsapp_integration

    tenant = Tenant(name="Outbound Timeout Tenant", slug=f"ott-{uuid.uuid4().hex[:6]}", is_active=True)
    test_session.add(tenant)
    await test_session.commit()

    app_secret = "secret_outbound_timeout_123"
    phone_number_id = "888444"
    await _setup_active_whatsapp_integration(tenant, test_session, phone_number_id=phone_number_id, app_secret=app_secret)

    provider_calls = 0

    async def mock_execute_op_timeout(*args, **kwargs):
        nonlocal provider_calls
        provider_calls += 1
        raise TimeoutError("WhatsApp API gateway connection timed out")

    monkeypatch.setattr(IntegrationService, "execute_operation", mock_execute_op_timeout)

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
                                    "from": "62812345679",
                                    "id": f"wamid.inbound_to_{uuid.uuid4().hex[:6]}",
                                    "timestamp": "1710000000",
                                    "type": "text",
                                    "text": {"body": "Tes timeout"},
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
    assert provider_calls == 1  # Verify NO blind retries took place

    # Verify outbound message transitioned to UNKNOWN
    from sqlalchemy import select
    outbound_msg = (await test_session.execute(select(Message).where(Message.tenant_id == tenant.id, Message.direction == "OUTBOUND"))).scalars().first()
    assert outbound_msg is not None
    assert outbound_msg.status == "UNKNOWN"


@pytest.mark.asyncio
async def test_r3_postgres_multi_session_human_takeover_race(test_session_factory):
    import asyncio
    from app.database.models import Tenant, Customer, Conversation, Message
    from app.repositories.domain import ConversationRepository, CustomerRepository, MessageRepository
    from app.core.router.router import MessageRouter

    async with test_session_factory() as session_setup:
        tenant = Tenant(name="Takeover Race Tenant", slug=f"trt-{uuid.uuid4().hex[:6]}", is_active=True)
        session_setup.add(tenant)
        await session_setup.commit()

        cust = await CustomerRepository(session_setup).get_or_create(tenant.id, "628123334444", name="Race Cust")
        conv = await ConversationRepository(session_setup).get_or_create_active(tenant.id, cust.id)
        msg = Message(
            tenant_id=tenant.id,
            conversation_id=conv.id,
            direction="INBOUND",
            message_type="TEXT",
            text="Berapa harga kemeja?",
        )
        session_setup.add(msg)
        await session_setup.commit()

        tenant_id = tenant.id
        conv_id = conv.id
        msg_id = msg.id

    # Session A: Worker A starts routing message
    async def worker_a_llm_generation():
        async with test_session_factory() as session_a:
            c_repo = ConversationRepository(session_a)
            m_repo = MessageRepository(session_a)

            conv_a = await c_repo.get_by_id(tenant_id, conv_id)
            msg_a = await m_repo.get_by_id(tenant_id, msg_id)

            router = MessageRouter()
            # Simulate async LLM generation pause
            await asyncio.sleep(0.1)

            res = await router.route_message(tenant_id, conv_a, msg_a, session_a)
            return res

    # Session B: Worker B concurrently claims human ownership
    async def worker_b_human_takeover():
        await asyncio.sleep(0.02)  # Ensure Worker A starts first
        async with test_session_factory() as session_b:
            c_repo = ConversationRepository(session_b)
            conv_b = await c_repo.get_by_id(tenant_id, conv_id)
            conv_b.human_handoff = True
            conv_b.status = "HUMAN_ACTIVE"
            await session_b.commit()

    res_a, _ = await asyncio.gather(worker_a_llm_generation(), worker_b_human_takeover())

    # Worker A must re-read DB status and suppress customer-facing AI response
    assert res_a.handsoff_to_human is True
    assert "[SYSTEM] Message logged for human agent." in res_a.response_text


@pytest.mark.asyncio
async def test_r3_direct_integration_service_no_blind_retry_on_send_message(test_session, monkeypatch):
    import uuid
    from unittest.mock import AsyncMock
    from app.database.models import Tenant
    from app.integrations.service import IntegrationService
    from app.integrations.registry import integration_registry
    from app.integrations.exceptions import TransientIntegrationError
    from tests.test_whatsapp_and_handoff import _setup_active_whatsapp_integration

    tenant = Tenant(name="Direct Retry Tenant", slug=f"drt-{uuid.uuid4().hex[:6]}", is_active=True)
    test_session.add(tenant)
    await test_session.commit()

    conn = await _setup_active_whatsapp_integration(tenant, test_session)

    service = IntegrationService(test_session)
    adapter = integration_registry.get_adapter("whatsapp_cloud_api")

    execute_calls = 0

    async def mock_adapter_execute(*args, **kwargs):
        nonlocal execute_calls
        execute_calls += 1
        raise TransientIntegrationError("Network timeout during provider send_message request")

    monkeypatch.setattr(adapter, "execute", mock_adapter_execute)

    # Directly invoke IntegrationService.execute_operation for send_message (returns OperationExecutionResult with status="FAILED")
    res = await service.execute_operation(
        tenant_id=tenant.id,
        connection_id=conn.id,
        operation="send_message",
        params={"recipient_phone": "62812345678", "text": "Direct send test"},
        allow_internal=True,
    )
    assert res.status == "FAILED"

    # Prove effective_retries=1 was enforced and adapter was invoked EXACTLY ONCE
    assert execute_calls == 1


@pytest.mark.asyncio
async def test_r3_outbound_test_matrix_a_to_f(async_client, test_session, monkeypatch):
    import json
    import hmac
    import hashlib
    from sqlalchemy import select
    from app.database.models import Tenant, Customer, Conversation, Message
    from app.database.models.integrations import IntegrationExecution
    from app.integrations.schemas import OperationExecutionResult
    from app.integrations.service import IntegrationService
    from tests.test_whatsapp_and_handoff import _setup_active_whatsapp_integration

    tenant = Tenant(name="Outbound Matrix Tenant", slug=f"omt-{uuid.uuid4().hex[:6]}", is_active=True)
    test_session.add(tenant)
    await test_session.commit()

    app_secret = "secret_matrix_123"
    phone_number_id = "999888"
    await _setup_active_whatsapp_integration(tenant, test_session, phone_number_id=phone_number_id, app_secret=app_secret)

    cust = Customer(tenant_id=tenant.id, name="Matrix Cust", phone="62812999000")
    test_session.add(cust)
    await test_session.commit()

    conv = Conversation(tenant_id=tenant.id, customer_id=cust.id, channel="whatsapp", status="OPEN")
    test_session.add(conv)
    await test_session.commit()

    # --- TEST D: Provider delivered status webhook (SENT -> DELIVERED) ---
    msg_d = Message(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="OUTBOUND",
        message_type="TEXT",
        status="SENT",
        text="Test D",
        external_message_id="wamid.matrix_d_001",
    )
    test_session.add(msg_d)
    await test_session.commit()

    payload_d = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_number_id}, "statuses": [{"id": "wamid.matrix_d_001", "status": "delivered", "timestamp": "1710000000", "recipient_id": "62812999000"}]}}]}]
    }
    raw_d = json.dumps(payload_d).encode("utf-8")
    sig_d = hmac.new(app_secret.encode("utf-8"), raw_d, hashlib.sha256).hexdigest()
    res_d = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_d, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig_d}"})
    assert res_d.status_code == 200
    assert res_d.json()["processed"][0]["status"] == "delivered"
    await test_session.refresh(msg_d)
    assert msg_d.status == "DELIVERED"

    # --- TEST E: Provider read status webhook (DELIVERED -> READ) ---
    payload_e = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_number_id}, "statuses": [{"id": "wamid.matrix_d_001", "status": "read", "timestamp": "1710000000", "recipient_id": "62812999000"}]}}]}]
    }
    raw_e = json.dumps(payload_e).encode("utf-8")
    sig_e = hmac.new(app_secret.encode("utf-8"), raw_e, hashlib.sha256).hexdigest()
    res_e = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_e, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig_e}"})
    assert res_e.status_code == 200
    assert res_e.json()["processed"][0]["status"] == "read"
    await test_session.refresh(msg_d)
    assert msg_d.status == "READ"

    # --- TEST F: Invalid status transition (CREATED + delivered) ---
    msg_f = Message(
        tenant_id=tenant.id,
        conversation_id=conv.id,
        direction="OUTBOUND",
        message_type="TEXT",
        status="CREATED",
        text="Test F",
        external_message_id="wamid.matrix_f_001",
    )
    test_session.add(msg_f)
    await test_session.commit()

    payload_f = {
        "object": "whatsapp_business_account",
        "entry": [{"id": "e1", "changes": [{"field": "messages", "value": {"metadata": {"phone_number_id": phone_number_id}, "statuses": [{"id": "wamid.matrix_f_001", "status": "delivered", "timestamp": "1710000000", "recipient_id": "62812999000"}]}}]}]
    }
    raw_f = json.dumps(payload_f).encode("utf-8")
    sig_f = hmac.new(app_secret.encode("utf-8"), raw_f, hashlib.sha256).hexdigest()
    res_f = await async_client.post("/api/v1/webhooks/whatsapp", content=raw_f, headers={"Content-Type": "application/json", "X-Hub-Signature-256": f"sha256={sig_f}"})
    assert res_f.status_code == 200
    assert res_f.json()["processed"][0]["status"] == "status_transition_rejected"

    await test_session.refresh(msg_f)
    assert msg_f.status == "CREATED"

    # Query DB and assert persistent IntegrationExecution record exists
    exec_stmt = select(IntegrationExecution).where(
        IntegrationExecution.tenant_id == tenant.id,
        IntegrationExecution.error_code == "INVALID_STATUS_TRANSITION",
    )
    rej_exec = (await test_session.execute(exec_stmt)).scalars().first()
    assert rej_exec is not None
    assert rej_exec.status == "FAILED"


@pytest.mark.asyncio
async def test_r3_postgres_multi_session_concurrency_matrix(test_session_factory):
    import asyncio
    from sqlalchemy import select
    from app.database.models import Tenant, Customer, Conversation, Message
    from app.database.models.integrations import IntegrationExecution
    from app.repositories.domain import CustomerRepository, ConversationRepository, MessageRepository

    # Setup baseline entities
    async with test_session_factory() as session_setup:
        tenant = Tenant(name="Concur Matrix Tenant", slug=f"cmt-{uuid.uuid4().hex[:6]}", is_active=True)
        session_setup.add(tenant)
        await session_setup.commit()

        tenant_id = tenant.id

    # 1. Message status transition race with with_for_update()
    async with test_session_factory() as session_m:
        cust_m = await CustomerRepository(session_m).get_or_create(tenant_id, "628120001111")
        conv_m = await ConversationRepository(session_m).get_or_create_active(tenant_id, cust_m.id)
        msg_m = Message(tenant_id=tenant_id, conversation_id=conv_m.id, direction="OUTBOUND", message_type="TEXT", status="CREATED")
        session_m.add(msg_m)
        await session_m.commit()
        msg_id = msg_m.id

    async def worker_trans_a():
        async with test_session_factory() as s_a:
            m_repo = MessageRepository(s_a)
            await m_repo.transition_status(tenant_id, msg_id, "QUEUED")
            await s_a.commit()

    async def worker_trans_b():
        await asyncio.sleep(0.01)
        async with test_session_factory() as s_b:
            m_repo = MessageRepository(s_b)
            await m_repo.transition_status(tenant_id, msg_id, "QUEUED")
            await s_b.commit()

    await asyncio.gather(worker_trans_a(), worker_trans_b())

    # 2. Customer get_or_create race
    async def worker_cust_a():
        async with test_session_factory() as s_a:
            repo = CustomerRepository(s_a)
            cust = await repo.get_or_create(tenant_id, "081299990000", name="Race Cust A")
            try:
                await s_a.commit()
            except Exception:
                await s_a.rollback()
                cust = await repo.get_by_phone(tenant_id, "081299990000")
            return cust.id

    async def worker_cust_b():
        await asyncio.sleep(0.01)
        async with test_session_factory() as s_b:
            repo = CustomerRepository(s_b)
            cust = await repo.get_or_create(tenant_id, "+6281299990000", name="Race Cust B")
            try:
                await s_b.commit()
            except Exception:
                await s_b.rollback()
                cust = await repo.get_by_phone(tenant_id, "+6281299990000")
            return cust.id

    c_id_a, c_id_b = await asyncio.gather(worker_cust_a(), worker_cust_b())
    assert c_id_a == c_id_b

    # 3. Active Conversation get_or_create_active race
    async def worker_conv_a():
        async with test_session_factory() as s_a:
            repo = ConversationRepository(s_a)
            conv = await repo.get_or_create_active(tenant_id, c_id_a, channel="whatsapp")
            try:
                await s_a.commit()
            except Exception:
                await s_a.rollback()
                conv = await repo.get_active_by_customer(tenant_id, c_id_a)
            return conv.id

    async def worker_conv_b():
        await asyncio.sleep(0.01)
        async with test_session_factory() as s_b:
            repo = ConversationRepository(s_b)
            conv = await repo.get_or_create_active(tenant_id, c_id_a, channel="whatsapp")
            try:
                await s_b.commit()
            except Exception:
                await s_b.rollback()
                conv = await repo.get_active_by_customer(tenant_id, c_id_a)
            return conv.id

    cv_id_a, cv_id_b = await asyncio.gather(worker_conv_a(), worker_conv_b())
    assert cv_id_a == cv_id_b

    # 4. IntegrationExecution idempotency race
    idempotency_key = f"race_exec_{uuid.uuid4().hex[:8]}"

    from tests.test_whatsapp_and_handoff import _setup_active_whatsapp_integration
    async with test_session_factory() as session_conn_setup:
        tenant_obj = (await session_conn_setup.execute(select(Tenant).where(Tenant.id == tenant_id))).scalar_one()
        conn_obj = await _setup_active_whatsapp_integration(tenant_obj, session_conn_setup)
        conn_id = conn_obj.id

    async def worker_exec_a():
        async with test_session_factory() as s_a:
            ex = IntegrationExecution(
                tenant_id=tenant_id,
                connection_id=conn_id,
                operation="race_op",
                status="COMPLETED",
                idempotency_key=idempotency_key,
            )
            s_a.add(ex)
            try:
                await s_a.commit()
            except Exception:
                await s_a.rollback()

    async def worker_exec_b():
        await asyncio.sleep(0.01)
        async with test_session_factory() as s_b:
            # Check idempotency prior to execution insert
            existing = (await s_b.execute(select(IntegrationExecution).where(IntegrationExecution.tenant_id == tenant_id, IntegrationExecution.idempotency_key == idempotency_key))).scalars().first()
            if not existing:
                ex = IntegrationExecution(
                    tenant_id=tenant_id,
                    connection_id=conn_id,
                    operation="race_op",
                    status="COMPLETED",
                    idempotency_key=idempotency_key,
                )
                s_b.add(ex)
                try:
                    await s_b.commit()
                except Exception:
                    await s_b.rollback()

    await asyncio.gather(worker_exec_a(), worker_exec_b())

    async with test_session_factory() as s_check:
        stmt = select(IntegrationExecution).where(IntegrationExecution.tenant_id == tenant_id, IntegrationExecution.idempotency_key == idempotency_key)
        execs = (await s_check.execute(stmt)).scalars().all()
        assert len(execs) == 1
