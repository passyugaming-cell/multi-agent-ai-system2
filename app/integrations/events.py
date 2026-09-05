import uuid
import logging
from typing import Any

from app.core.events.publisher import get_event_bus
from app.core.events.schemas import EventSchema

logger = logging.getLogger(__name__)


async def publish_integration_event(
    tenant_id: uuid.UUID | str,
    event_type: str,
    payload: dict[str, Any],
    source: str = "integration_service",
    correlation_id: str | None = None,
    causation_id: str | None = None,
    idempotency_key: str | None = None,
) -> None:
    """Emits Phase 6 integration events to Phase 2 EventBus."""
    bus = get_event_bus()
    evt_id = f"evt_int_{uuid.uuid4().hex[:12]}"

    event = EventSchema(
        event_id=evt_id,
        tenant_id=str(tenant_id),
        event_type=event_type,
        payload=payload,
        source=source,
        correlation_id=correlation_id,
        causation_id=causation_id,
        idempotency_key=idempotency_key,
    )

    try:
        await bus.publish(event)
        logger.info("Published integration event %s (type: %s) for tenant %s", evt_id, event_type, tenant_id)
    except Exception as e:
        logger.error("Failed to publish integration event %s: %s", evt_id, e)
