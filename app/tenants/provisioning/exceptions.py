from app.core.exceptions import AppException


class ProvisioningError(AppException):
    """Base exception for provisioning failures."""

    def __init__(self, message: str = "Tenant provisioning failed"):
        super().__init__(
            code="PROVISIONING_ERROR",
            message=message,
            status_code=400,
        )


class InvalidLifecycleTransitionError(AppException):
    """Exception raised when an invalid client lifecycle transition is attempted."""

    def __init__(self, from_state: str, to_state: str, reason: str | None = None):
        msg = f"Invalid lifecycle transition from '{from_state}' to '{to_state}'"
        if reason:
            msg += f": {reason}"
        super().__init__(
            code="INVALID_LIFECYCLE_TRANSITION",
            message=msg,
            status_code=400,
        )


class ChecklistRequirementError(AppException):
    """Exception raised when a required checklist operation fails."""

    def __init__(self, message: str = "Checklist requirement validation failed"):
        super().__init__(
            code="CHECKLIST_REQUIREMENT_ERROR",
            message=message,
            status_code=400,
        )


class ReadinessValidationError(AppException):
    """Exception raised when readiness validation fails."""

    def __init__(self, message: str = "Tenant is not ready for operation"):
        super().__init__(
            code="TENANT_NOT_READY",
            message=message,
            status_code=400,
        )
