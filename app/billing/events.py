import uuid
import logging
from typing import Any

from app.core.events import get_event_bus
from app.core.events.schemas import EventSchema

logger = logging.getLogger("app.billing.events")


async def publish_billing_event(
    event_type: str,
    tenant_id: uuid.UUID | str,
    payload: dict[str, Any],
    source: str = "billing_service",
) -> None:
    """Helper to publish billing domain events via the central Event Bus."""
    try:
        bus = get_event_bus()
        event = EventSchema(
            event_id=f"evt_bill_{uuid.uuid4().hex[:12]}",
            tenant_id=str(tenant_id),
            event_type=event_type,
            payload=payload,
            source=source,
        )
        await bus.publish(event)
    except Exception as e:
        logger.warning(f"Failed to publish billing event '{event_type}' for tenant {tenant_id}: {e}")
