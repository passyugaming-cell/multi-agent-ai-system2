from datetime import datetime, timezone
from uuid import UUID
from app.integrations.whatsapp.schemas import WhatsAppWebhookPayload
from app.integrations.whatsapp.exceptions import WhatsAppParsingError
from app.schemas.universal_message import UniversalMessage


class WhatsAppParser:
    """Parses WhatsApp provider payload into UniversalMessage objects."""

    @staticmethod
    def parse_payload(tenant_id: UUID, payload_dict: dict) -> list[UniversalMessage]:
        universal_messages: list[UniversalMessage] = []

        try:
            payload = WhatsAppWebhookPayload.model_validate(payload_dict)
        except Exception as exc:
            raise WhatsAppParsingError(f"Failed to validate WhatsApp payload schema: {exc}")

        for entry in payload.entry:
            for change in entry.changes:
                value = change.value
                contacts_map = {}
                if value.contacts:
                    for contact in value.contacts:
                        contacts_map[contact.wa_id] = contact.profile.name if contact.profile else None

                if not value.messages:
                    continue

                for msg in value.messages:
                    sender_phone = msg.from_
                    msg_id = msg.id
                    msg_type = msg.type.upper()
                    if msg_type not in ["TEXT", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT"]:
                        msg_type = "OTHER"

                    text_content = None
                    if msg.text:
                        text_content = msg.text.body
                    elif msg.image and msg.image.caption:
                        text_content = msg.image.caption

                    ts = datetime.now(timezone.utc)
                    if msg.timestamp:
                        try:
                            ts = datetime.fromtimestamp(int(msg.timestamp), tz=timezone.utc)
                        except Exception:
                            pass

                    customer_name = contacts_map.get(sender_phone)

                    universal_msg = UniversalMessage(
                        tenant_id=tenant_id,
                        channel="whatsapp",
                        external_message_id=msg_id,
                        direction="INBOUND",
                        message_type=msg_type,
                        text=text_content,
                        timestamp=ts,
                        metadata={
                            "sender_phone": sender_phone,
                            "sender_name": customer_name,
                            "raw_type": msg.type,
                        },
                    )
                    universal_messages.append(universal_msg)

        return universal_messages
