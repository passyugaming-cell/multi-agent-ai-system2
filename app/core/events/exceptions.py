class EventBusException(Exception):
    """Base exception for Event Bus errors."""
    pass


class InvalidTenantContextError(EventBusException):
    """Raised when event processing encounters invalid tenant context."""
    pass


class EventPublishError(EventBusException):
    """Raised when an event fails to publish."""
    pass


class EventSubscriptionError(EventBusException):
    """Raised when subscribing a handler fails."""
    pass


class DuplicateEventError(EventBusException):
    """Raised when duplicate event delivery is detected."""
    pass
