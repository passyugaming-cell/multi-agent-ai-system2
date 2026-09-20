import logging
from enum import Enum
from typing import Set
from app.core.exceptions import AppException
from app.integrations.exceptions import InvalidStateTransitionError

logger = logging.getLogger(__name__)


class IntegrationConnectionStatus(str, Enum):
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    ACTIVE = "ACTIVE"
    ERROR = "ERROR"
    RECONNECTING = "RECONNECTING"
    EXPIRED = "EXPIRED"
    REVOKED = "REVOKED"
    DISABLED = "DISABLED"


ALLOWED_INTEGRATION_TRANSITIONS: dict[IntegrationConnectionStatus, Set[IntegrationConnectionStatus]] = {
    IntegrationConnectionStatus.DISCONNECTED: {
        IntegrationConnectionStatus.CONNECTING,
        IntegrationConnectionStatus.DISABLED,
    },
    IntegrationConnectionStatus.CONNECTING: {
        IntegrationConnectionStatus.CONNECTED,
        IntegrationConnectionStatus.ERROR,
        IntegrationConnectionStatus.DISCONNECTED,
    },
    IntegrationConnectionStatus.CONNECTED: {
        IntegrationConnectionStatus.ACTIVE,
        IntegrationConnectionStatus.ERROR,
        IntegrationConnectionStatus.EXPIRED,
        IntegrationConnectionStatus.REVOKED,
        IntegrationConnectionStatus.DISCONNECTED,
    },
    IntegrationConnectionStatus.ACTIVE: {
        IntegrationConnectionStatus.CONNECTING,
        IntegrationConnectionStatus.RECONNECTING,
        IntegrationConnectionStatus.CONNECTED,
        IntegrationConnectionStatus.ERROR,
        IntegrationConnectionStatus.EXPIRED,
        IntegrationConnectionStatus.REVOKED,
        IntegrationConnectionStatus.DISABLED,
        IntegrationConnectionStatus.DISCONNECTED,
    },
    IntegrationConnectionStatus.RECONNECTING: {
        IntegrationConnectionStatus.CONNECTED,
        IntegrationConnectionStatus.ACTIVE,
        IntegrationConnectionStatus.ERROR,
        IntegrationConnectionStatus.EXPIRED,
        IntegrationConnectionStatus.REVOKED,
        IntegrationConnectionStatus.DISCONNECTED,
    },
    IntegrationConnectionStatus.ERROR: {
        IntegrationConnectionStatus.RECONNECTING,
        IntegrationConnectionStatus.CONNECTING,
        IntegrationConnectionStatus.DISCONNECTED,
        IntegrationConnectionStatus.DISABLED,
    },
    IntegrationConnectionStatus.EXPIRED: {
        IntegrationConnectionStatus.CONNECTING,
        IntegrationConnectionStatus.DISCONNECTED,
        IntegrationConnectionStatus.DISABLED,
    },
    IntegrationConnectionStatus.REVOKED: {
        IntegrationConnectionStatus.CONNECTING,
        IntegrationConnectionStatus.DISCONNECTED,
        IntegrationConnectionStatus.DISABLED,
    },
    IntegrationConnectionStatus.DISABLED: {
        IntegrationConnectionStatus.DISCONNECTED,
        IntegrationConnectionStatus.CONNECTING,
    },
}


def validate_integration_connection_transition(current_status: str, target_status: str) -> None:
    """Enforces state transition rules for IntegrationConnection entities."""
    if current_status == target_status:
        return

    try:
        curr_enum = IntegrationConnectionStatus(current_status)
    except ValueError:
        raise InvalidStateTransitionError(current_status, target_status)

    try:
        target_enum = IntegrationConnectionStatus(target_status)
    except ValueError:
        raise InvalidStateTransitionError(current_status, target_status)

    allowed = ALLOWED_INTEGRATION_TRANSITIONS.get(curr_enum, set())
    if target_enum not in allowed:
        logger.warning(
            "Rejected invalid integration connection transition: '%s' -> '%s'",
            current_status,
            target_status,
        )
        raise InvalidStateTransitionError(current_status, target_status)
