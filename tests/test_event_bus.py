import uuid
import pytest
from datetime import datetime, timezone
from app.core.events.schemas import EventSchema
from app.core.events.backends.in_memory import InMemoryEventBus
from app.core.events.backends.redis import RedisEventBus
from app.core.events.exceptions import InvalidTenantContextError


@pytest.mark.asyncio
async def test_event_schema_valid():
    tenant_id = str(uuid.uuid4())
    event = EventSchema(
        event_id="evt_123",
        tenant_id=tenant_id,
        event_type="order.created",
        occurred_at=datetime.now(timezone.utc),
        payload={"order_id": "ord_999", "total": 150.0},
        source="order_service",
    )
    assert event.event_id == "evt_123"
    assert event.tenant_id == tenant_id
    assert event.schema_version == 1


@pytest.mark.asyncio
async def test_event_schema_invalid_tenant():
    with pytest.raises(ValueError):
        EventSchema(
            event_id="evt_123",
            tenant_id="invalid-uuid",
            event_type="order.created",
            source="order_service",
        )


@pytest.mark.asyncio
async def test_event_schema_rejects_secrets():
    tenant_id = str(uuid.uuid4())
    with pytest.raises(ValueError, match="must not contain secret fields"):
        EventSchema(
            event_id="evt_123",
            tenant_id=tenant_id,
            event_type="user.login",
            payload={"username": "alice", "password": "supersecretpassword"},
            source="auth_service",
        )


@pytest.mark.asyncio
async def test_in_memory_event_bus():
    bus = InMemoryEventBus()
    received_events = []

    async def sample_handler(event: EventSchema):
        received_events.append(event)

    await bus.subscribe("order.created", sample_handler)

    tenant_id = str(uuid.uuid4())
    event = EventSchema(
        event_id="evt_101",
        tenant_id=tenant_id,
        event_type="order.created",
        payload={"order_id": "ord_101"},
        source="order_service",
    )

    await bus.publish(event)
    assert len(received_events) == 1
    assert received_events[0].event_id == "evt_101"
    assert received_events[0].tenant_id == tenant_id


@pytest.mark.asyncio
async def test_redis_event_bus_integration():
    tenant_id = str(uuid.uuid4())
    bus = RedisEventBus(redis_url="redis://localhost:6379/0", consumer_name="test_worker")
    received_events = []

    async def sample_handler(event: EventSchema):
        received_events.append(event)

    await bus.subscribe("customer.created", sample_handler)

    try:
        await bus.start()
        event = EventSchema(
            event_id="evt_redis_1",
            tenant_id=tenant_id,
            event_type="customer.created",
            payload={"customer_id": "cust_1"},
            source="customer_service",
        )
        await bus.publish(event)

        # Allow consumer loop to fetch message
        import asyncio
        await asyncio.sleep(0.5)

        assert len(received_events) == 1
        assert received_events[0].event_id == "evt_redis_1"
        assert received_events[0].tenant_id == tenant_id
    finally:
        await bus.stop()
