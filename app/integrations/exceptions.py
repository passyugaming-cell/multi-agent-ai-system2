class IntegrationError(Exception):
    """Base exception for integration module."""
    pass


class IntegrationNotFoundError(IntegrationError):
    """Raised when an integration catalog item is not found."""
    def __init__(self, key_or_id: str):
        super().__init__(f"Integration not found: {key_or_id}")


class ConnectionNotFoundError(IntegrationError):
    """Raised when an integration connection is not found."""
    def __init__(self, connection_id: str):
        super().__init__(f"Integration connection not found: {connection_id}")


class CredentialNotFoundError(IntegrationError):
    """Raised when integration credentials are missing."""
    def __init__(self, connection_id: str):
        super().__init__(f"Credentials not found for connection: {connection_id}")


class InvalidStateTransitionError(IntegrationError):
    """Raised when an invalid lifecycle state transition is attempted."""
    def __init__(self, current_status: str, target_status: str):
        super().__init__(f"Invalid connection status transition from {current_status} to {target_status}")


class CredentialSecurityError(IntegrationError):
    """Raised on encryption, decryption, or key security failure."""
    pass


class WebhookVerificationError(IntegrationError):
    """Raised when inbound webhook signature validation fails."""
    pass


class IntegrationExecutionError(IntegrationError):
    """Base execution error for external operations."""
    def __init__(self, message: str, error_code: str | None = None):
        self.error_code = error_code or "EXECUTION_ERROR"
        super().__init__(message)


class TransientIntegrationError(IntegrationExecutionError):
    """Temporary failure suitable for retries (e.g., timeout, rate limit, temporary 5xx)."""
    pass


class PermanentIntegrationError(IntegrationExecutionError):
    """Permanent failure that should not be retried (e.g., 401 Unauthorized, 404, invalid body)."""
    pass


class RateLimitExceededError(TransientIntegrationError):
    """Raised when external provider rate limits are exceeded."""
    def __init__(self, provider: str, retry_after: int = 60):
        self.provider = provider
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded for provider {provider}. Retry after {retry_after}s", error_code="RATE_LIMIT_EXCEEDED")


class EntitlementDeniedError(IntegrationError):
    """Raised when tenant plan does not support requested integration feature."""
    def __init__(self, feature_key: str):
        super().__init__(f"Tenant entitlement check failed for feature: {feature_key}")


class PermissionDeniedError(IntegrationError):
    """Raised when user/actor lacks required permission for integration action."""
    def __init__(self, permission: str):
        super().__init__(f"Permission denied: missing {permission}")
