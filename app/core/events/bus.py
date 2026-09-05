from abc import ABC, abstractmethod
from typing import Callable, Awaitable, Any
from app.core.events.schemas import EventSchema

EventHandler = Callable[[EventSchema], Awaitable[None]]


class EventBusInterface(ABC):
    """Abstract interface for Event Bus operations."""

    @abstractmethod
    async def publish(self, event: EventSchema) -> None:
        """Publish an event to the bus."""
        pass

    @abstractmethod
    async def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """Subscribe an async handler to a specific event type."""
        pass

    @abstractmethod
    async def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Unsubscribe a handler from a specific event type."""
        pass

    @abstractmethod
    async def start(self) -> None:
        """Start listening/processing events if background tasks/connections required."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop background workers and clean up connections."""
        pass
