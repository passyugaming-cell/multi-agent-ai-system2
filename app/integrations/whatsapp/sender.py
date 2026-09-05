import logging
from uuid import UUID
from app.schemas.universal_message import UniversalMessage

logger = logging.getLogger("integrations.whatsapp.sender")


class WhatsAppSender:
    """Outbound sender abstraction for WhatsApp messages."""

    def __init__(self, is_development: bool = True):
        self.is_development = is_development

    async def send_message(self, tenant_id: UUID, recipient_phone: str, message_text: str) -> dict:
        """Sends an outbound WhatsApp message or simulates delivery in development mode."""
        if self.is_development:
            logger.info(
                f"[SIMULATED WHATSAPP OUTBOUND] Tenant: {tenant_id} | To: {recipient_phone} | Message: {message_text}"
            )
            return {
                "status": "SIMULATED",
                "tenant_id": str(tenant_id),
                "recipient_phone": recipient_phone,
                "text": message_text,
                "provider_message_id": f"sim_wa_msg_{tenant_id.hex[:8]}",
            }

        raise NotImplementedError("Production WhatsApp provider integration is not configured.")
