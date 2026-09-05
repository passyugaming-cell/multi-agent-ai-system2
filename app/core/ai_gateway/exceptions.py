class AIGatewayError(Exception):
    """Base exception for AI Gateway errors."""

    pass


class AITimeoutError(AIGatewayError):
    """Raised when an AI request times out."""

    pass


class AIRateLimitError(AIGatewayError):
    """Raised when an AI request exceeds rate limits or quota."""

    pass


class AIAuthenticationError(AIGatewayError):
    """Raised when authentication with the AI provider fails."""

    pass


class AIProviderUnavailableError(AIGatewayError):
    """Raised when the AI provider service is down or unreachable."""

    pass


class AIInvalidRequestError(AIGatewayError):
    """Raised when the request parameters sent to AI provider are invalid."""

    pass


class AIMalformedResponseError(AIGatewayError):
    """Raised when the AI provider returns a malformed or unparseable response."""

    pass
