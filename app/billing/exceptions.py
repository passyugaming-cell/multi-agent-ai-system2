from app.core.exceptions import AppError


class BillingError(AppError):
    """Base exception for billing domain errors."""

    def __init__(self, message: str, code: str = "BILLING_ERROR", status_code: int = 400) -> None:
        super().__init__(message=message, code=code, status_code=status_code)


class PlanNotFoundError(BillingError):
    def __init__(self, plan_identifier: str) -> None:
        super().__init__(
            message=f"Plan '{plan_identifier}' not found.",
            code="PLAN_NOT_FOUND",
            status_code=404,
        )


class SubscriptionNotFoundError(BillingError):
    def __init__(self, tenant_id: str) -> None:
        super().__init__(
            message=f"Subscription for tenant '{tenant_id}' not found.",
            code="SUBSCRIPTION_NOT_FOUND",
            status_code=404,
        )


class InvalidSubscriptionStateError(BillingError):
    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            message=f"Invalid subscription transition from '{current_status}' to '{target_status}'.",
            code="INVALID_SUBSCRIPTION_STATE_TRANSITION",
            status_code=400,
        )


class InvalidInvoiceStateError(BillingError):
    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            message=f"Invalid invoice transition from '{current_status}' to '{target_status}'.",
            code="INVALID_INVOICE_STATE_TRANSITION",
            status_code=400,
        )


class InvalidPaymentStateError(BillingError):
    def __init__(self, current_status: str, target_status: str) -> None:
        super().__init__(
            message=f"Invalid payment transition from '{current_status}' to '{target_status}'.",
            code="INVALID_PAYMENT_STATE_TRANSITION",
            status_code=400,
        )


class EntitlementDeniedError(BillingError):
    def __init__(self, feature_key: str, reason: str = "Feature not allowed in current plan/subscription") -> None:
        super().__init__(
            message=f"Access denied for feature '{feature_key}': {reason}",
            code="ENTITLEMENT_DENIED",
            status_code=403,
        )


class LimitExceededError(BillingError):
    def __init__(self, metric: str, current: int, limit: int) -> None:
        super().__init__(
            message=f"Resource limit exceeded for '{metric}': {current}/{limit}.",
            code="LIMIT_EXCEEDED",
            status_code=429,
        )


class InvoiceNotFoundError(BillingError):
    def __init__(self, invoice_id: str) -> None:
        super().__init__(
            message=f"Invoice '{invoice_id}' not found.",
            code="INVOICE_NOT_FOUND",
            status_code=404,
        )


class PaymentFailedError(BillingError):
    def __init__(self, reason: str) -> None:
        super().__init__(
            message=f"Payment processing failed: {reason}",
            code="PAYMENT_FAILED",
            status_code=400,
        )


class WebhookVerificationError(BillingError):
    def __init__(self, message: str = "Payment webhook signature verification failed.") -> None:
        super().__init__(
            message=message,
            code="WEBHOOK_VERIFICATION_FAILED",
            status_code=401,
        )
