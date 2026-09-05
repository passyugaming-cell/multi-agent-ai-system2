from typing import Any, Optional


class AppException(Exception):
    """Base exception for application errors."""

    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: Optional[dict[str, Any]] = None,
    ):
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
        super().__init__(message)


class MissingTenantHeaderException(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="MISSING_TENANT_HEADER",
            message="X-Tenant-ID header is required",
            status_code=400,
        )


class InvalidTenantIdException(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="INVALID_TENANT_ID",
            message="X-Tenant-ID header must be a valid UUID",
            status_code=400,
        )


class TenantNotFoundException(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="TENANT_NOT_FOUND",
            message="Tenant not found",
            status_code=404,
        )


class TenantInactiveException(AppException):
    def __init__(self) -> None:
        super().__init__(
            code="TENANT_INACTIVE",
            message="Tenant is inactive",
            status_code=403,
        )
