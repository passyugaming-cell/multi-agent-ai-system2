import asyncio
import logging
from collections import defaultdict
from app.core.events.bus import EventBusInterface, EventHandler
from app.core.events.schemas import EventSchema
from app.core.events.exceptions import InvalidTenantContextError

logger = logging.getLogger(__name__)


class InMemoryEventBus(EventBusInterface):
    """In-memory event bus implementation for testing and development."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._processed_events: set[str] = set()

    async def publish(self, event: EventSchema) -> None:
        if not event.tenant_id:
            raise InvalidTenantContextError("Event lacks tenant_id")

        handlers = list(self._handlers.get(event.event_type, [])) + list(self._handlers.get("*", []))

        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                logger.error("Error executing handler for event %s: %s", event.event_id, e, exc_info=True)

    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler not in self._handlers[event_type]:
            self._handlers[event_type].append(handler)

    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        if handler in self._handlers[event_type]:
            self._handlers[event_type].remove(handler)

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        self._handlers.clear()
