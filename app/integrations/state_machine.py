import logging
from enum import Enum
from typing import Set
from app.core.exceptions import AppException

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
        IntegrationConnectionStatus.RECONNECTING,
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
        raise AppException(
            code="INVALID_INTEGRATION_STATE_TRANSITION",
            message=f"Unknown current integration connection status: '{current_status}'.",
            status_code=400,
        )

    try:
        target_enum = IntegrationConnectionStatus(target_status)
    except ValueError:
        raise AppException(
            code="INVALID_INTEGRATION_STATE_TRANSITION",
            message=f"Unknown target integration connection status: '{target_status}'.",
            status_code=400,
        )

    allowed = ALLOWED_INTEGRATION_TRANSITIONS.get(curr_enum, set())
    if target_enum not in allowed:
        logger.warning(
            "Rejected invalid integration connection transition: '%s' -> '%s'",
            current_status,
            target_status,
        )
        raise AppException(
            code="INVALID_INTEGRATION_STATE_TRANSITION",
            message=f"Cannot transition integration connection status from '{current_status}' to '{target_status}'.",
            status_code=400,
        )
