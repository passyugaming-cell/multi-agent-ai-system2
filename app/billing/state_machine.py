from typing import Set
from app.billing.exceptions import (
    InvalidSubscriptionStateError,
    InvalidInvoiceStateError,
    InvalidPaymentStateError,
)


class SubscriptionStatus:
    TRIALING = "TRIALING"
    ACTIVE = "ACTIVE"
    PAST_DUE = "PAST_DUE"
    GRACE_PERIOD = "GRACE_PERIOD"
    RESTRICTED = "RESTRICTED"
    SUSPENDED = "SUSPENDED"
    CANCELLED_PENDING_EXPIRY = "CANCELLED_PENDING_EXPIRY"
    EXPIRED = "EXPIRED"
    ARCHIVED = "ARCHIVED"


class InvoiceStatus:
    DRAFT = "DRAFT"
    ISSUED = "ISSUED"
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"
    VOID = "VOID"
    OVERDUE = "OVERDUE"


class PaymentStatus:
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REFUNDED = "REFUNDED"
    PARTIALLY_REFUNDED = "PARTIALLY_REFUNDED"
    CANCELLED = "CANCELLED"


SUBSCRIPTION_TRANSITIONS: dict[str, Set[str]] = {
    SubscriptionStatus.TRIALING: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.EXPIRED,
        SubscriptionStatus.CANCELLED_PENDING_EXPIRY,
        SubscriptionStatus.PAST_DUE,
    },
    SubscriptionStatus.ACTIVE: {
        SubscriptionStatus.PAST_DUE,
        SubscriptionStatus.CANCELLED_PENDING_EXPIRY,
        SubscriptionStatus.RESTRICTED,
        SubscriptionStatus.SUSPENDED,
        SubscriptionStatus.EXPIRED,
    },
    SubscriptionStatus.PAST_DUE: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.GRACE_PERIOD,
        SubscriptionStatus.RESTRICTED,
        SubscriptionStatus.SUSPENDED,
        SubscriptionStatus.EXPIRED,
    },
    SubscriptionStatus.GRACE_PERIOD: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.RESTRICTED,
        SubscriptionStatus.SUSPENDED,
        SubscriptionStatus.EXPIRED,
    },
    SubscriptionStatus.RESTRICTED: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.SUSPENDED,
        SubscriptionStatus.EXPIRED,
    },
    SubscriptionStatus.SUSPENDED: {
        SubscriptionStatus.ACTIVE,
        SubscriptionStatus.EXPIRED,
    },
    SubscriptionStatus.CANCELLED_PENDING_EXPIRY: {
        SubscriptionStatus.EXPIRED,
        SubscriptionStatus.ACTIVE,
    },
    SubscriptionStatus.EXPIRED: {
        SubscriptionStatus.ARCHIVED,
        SubscriptionStatus.ACTIVE,
    },
    SubscriptionStatus.ARCHIVED: set(),
}

INVOICE_TRANSITIONS: dict[str, Set[str]] = {
    InvoiceStatus.DRAFT: {
        InvoiceStatus.ISSUED,
        InvoiceStatus.VOID,
    },
    InvoiceStatus.ISSUED: {
        InvoiceStatus.PENDING,
        InvoiceStatus.PAID,
        InvoiceStatus.FAILED,
        InvoiceStatus.VOID,
    },
    InvoiceStatus.PENDING: {
        InvoiceStatus.PAID,
        InvoiceStatus.FAILED,
        InvoiceStatus.OVERDUE,
        InvoiceStatus.VOID,
    },
    InvoiceStatus.FAILED: {
        InvoiceStatus.PENDING,
        InvoiceStatus.PAID,
        InvoiceStatus.OVERDUE,
        InvoiceStatus.VOID,
    },
    InvoiceStatus.OVERDUE: {
        InvoiceStatus.PAID,
        InvoiceStatus.FAILED,
        InvoiceStatus.VOID,
    },
    InvoiceStatus.PAID: set(),
    InvoiceStatus.VOID: set(),
}

PAYMENT_TRANSITIONS: dict[str, Set[str]] = {
    PaymentStatus.PENDING: {
        PaymentStatus.SUCCEEDED,
        PaymentStatus.FAILED,
        PaymentStatus.CANCELLED,
    },
    PaymentStatus.SUCCEEDED: {
        PaymentStatus.REFUNDED,
        PaymentStatus.PARTIALLY_REFUNDED,
    },
    PaymentStatus.FAILED: {
        PaymentStatus.PENDING,
    },
    PaymentStatus.PARTIALLY_REFUNDED: {
        PaymentStatus.REFUNDED,
    },
    PaymentStatus.REFUNDED: set(),
    PaymentStatus.CANCELLED: set(),
}


def validate_subscription_transition(current_status: str, new_status: str) -> None:
    if current_status == new_status:
        return
    allowed = SUBSCRIPTION_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise InvalidSubscriptionStateError(current_status, new_status)


def validate_invoice_transition(current_status: str, new_status: str) -> None:
    if current_status == new_status:
        return
    allowed = INVOICE_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise InvalidInvoiceStateError(current_status, new_status)


def validate_payment_transition(current_status: str, new_status: str) -> None:
    if current_status == new_status:
        return
    allowed = PAYMENT_TRANSITIONS.get(current_status, set())
    if new_status not in allowed:
        raise InvalidPaymentStateError(current_status, new_status)
