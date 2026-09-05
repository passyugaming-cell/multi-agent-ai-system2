class WhatsAppError(Exception):
    """Base exception for WhatsApp adapter errors."""

    pass


class WhatsAppParsingError(WhatsAppError):
    """Raised when parsing WhatsApp webhook payload fails."""

    pass


class WhatsAppWebhookVerificationError(WhatsAppError):
    """Raised when webhook verification/signature check fails."""

    pass
