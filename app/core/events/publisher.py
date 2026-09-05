import logging
from app.core.config import settings
from app.core.events.bus import EventBusInterface
from app.core.events.backends.in_memory import InMemoryEventBus
from app.core.events.backends.redis import RedisEventBus

logger = logging.getLogger(__name__)

_global_event_bus: EventBusInterface | None = None


def get_event_bus() -> EventBusInterface:
    """Get or create singleton instance of the configured Event Bus."""
    global _global_event_bus
    if _global_event_bus is None:
        if settings.EVENT_BUS_BACKEND == "redis":
            _global_event_bus = RedisEventBus(redis_url=settings.REDIS_URL)
        else:
            _global_event_bus = InMemoryEventBus()
    return _global_event_bus


def set_event_bus(bus: EventBusInterface) -> None:
    """Override current global Event Bus (useful for unit tests)."""
    global _global_event_bus
    _global_event_bus = bus
