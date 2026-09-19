import logging
from enum import Enum
from typing import Set
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)


class OrderStatus(str, Enum):
    CART = "CART"
    PENDING_CONFIRMATION = "PENDING_CONFIRMATION"
    ORDER_CREATED = "ORDER_CREATED"
    PAYMENT_PENDING = "PAYMENT_PENDING"
    PAID = "PAID"
    PROCESSING = "PROCESSING"
    FULFILLED = "FULFILLED"
    COMPLETED = "COMPLETED"

    CANCELLED = "CANCELLED"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    EXPIRED = "EXPIRED"
    REFUND_PENDING = "REFUND_PENDING"
    REFUNDED = "REFUNDED"
    RETURN_REQUESTED = "RETURN_REQUESTED"
    RETURNED = "RETURNED"
    EXCHANGE_REQUESTED = "EXCHANGE_REQUESTED"


class InvalidOrderStateTransitionError(AppException):
    def __init__(self, current_status: str, target_status: str):
        super().__init__(
            code="INVALID_ORDER_STATE_TRANSITION",
            message=f"Cannot transition order status from '{current_status}' to '{target_status}'.",
            status_code=400,
        )


ALLOWED_ORDER_TRANSITIONS: dict[OrderStatus, Set[OrderStatus]] = {
    OrderStatus.CART: {
        OrderStatus.PENDING_CONFIRMATION,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    },
    OrderStatus.PENDING_CONFIRMATION: {
        OrderStatus.ORDER_CREATED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    },
    OrderStatus.ORDER_CREATED: {
        OrderStatus.PAYMENT_PENDING,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    },
    OrderStatus.PAYMENT_PENDING: {
        OrderStatus.PAID,
        OrderStatus.PAYMENT_FAILED,
        OrderStatus.CANCELLED,
        OrderStatus.EXPIRED,
    },
    OrderStatus.PAID: {
        OrderStatus.PROCESSING,
        OrderStatus.REFUND_PENDING,
        OrderStatus.REFUNDED,
        OrderStatus.CANCELLED,
    },
    OrderStatus.PROCESSING: {
        OrderStatus.FULFILLED,
        OrderStatus.REFUND_PENDING,
        OrderStatus.CANCELLED,
    },
    OrderStatus.FULFILLED: {
        OrderStatus.COMPLETED,
        OrderStatus.RETURN_REQUESTED,
        OrderStatus.EXCHANGE_REQUESTED,
        OrderStatus.REFUND_PENDING,
    },
    OrderStatus.COMPLETED: {
        OrderStatus.RETURN_REQUESTED,
        OrderStatus.EXCHANGE_REQUESTED,
        OrderStatus.REFUND_PENDING,
        OrderStatus.REFUNDED,
    },
    OrderStatus.REFUND_PENDING: {
        OrderStatus.REFUNDED,
        OrderStatus.PAID,
        OrderStatus.PROCESSING,
    },
    OrderStatus.RETURN_REQUESTED: {
        OrderStatus.RETURNED,
        OrderStatus.COMPLETED,
    },
    OrderStatus.EXCHANGE_REQUESTED: {
        OrderStatus.FULFILLED,
        OrderStatus.COMPLETED,
    },
    OrderStatus.PAYMENT_FAILED: {
        OrderStatus.PAYMENT_PENDING,
        OrderStatus.CANCELLED,
    },
    OrderStatus.CANCELLED: set(),
    OrderStatus.EXPIRED: set(),
    OrderStatus.REFUNDED: set(),
    OrderStatus.RETURNED: set(),
}


VALID_INITIAL_ORDER_STATUSES: Set[str] = {
    OrderStatus.CART.value,
    OrderStatus.PENDING_CONFIRMATION.value,
    OrderStatus.ORDER_CREATED.value,
}


def validate_initial_order_status(initial_status: str) -> None:
    """Validates that an Order is created only in a canonical initial state."""
    if initial_status not in VALID_INITIAL_ORDER_STATUSES:
        logger.warning("Rejected invalid initial order status creation: '%s'", initial_status)
        raise ValueError(
            f"INVALID_INITIAL_ORDER_STATUS: Order cannot be created directly in state '{initial_status}'. "
            f"Valid initial states are {sorted(list(VALID_INITIAL_ORDER_STATUSES))}."
        )


def validate_order_status_transition(current_status: str, target_status: str) -> None:
    """Validates Order state transition according to ACT-111 state machine rules."""
    if current_status == target_status:
        return

    try:
        curr_enum = OrderStatus(current_status)
    except ValueError:
        raise InvalidOrderStateTransitionError(current_status, target_status)

    try:
        target_enum = OrderStatus(target_status)
    except ValueError:
        raise InvalidOrderStateTransitionError(current_status, target_status)

    allowed = ALLOWED_ORDER_TRANSITIONS.get(curr_enum, set())
    if target_enum not in allowed:
        logger.warning("Rejected invalid order state transition: '%s' -> '%s'", current_status, target_status)
        raise InvalidOrderStateTransitionError(current_status, target_status)
