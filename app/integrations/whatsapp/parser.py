from datetime import datetime, timezone
import logging
from uuid import UUID
from app.core.phone import normalize_phone_number, PhoneNormalizationError
from app.integrations.whatsapp.schemas import WhatsAppWebhookPayload
from app.integrations.whatsapp.exceptions import WhatsAppParsingError
from app.schemas.universal_message import UniversalMessage

logger = logging.getLogger(__name__)


class WhatsAppParser:
    """Parses WhatsApp provider payload into UniversalMessage objects safely."""

    @staticmethod
    def parse_payload(tenant_id: UUID, payload_dict: dict) -> list[UniversalMessage]:
        universal_messages: list[UniversalMessage] = []

        try:
            payload = WhatsAppWebhookPayload.model_validate(payload_dict)
        except Exception as exc:
            logger.warning(f"Payload model validation failed, proceeding with safe dict fallback: {exc}")
            payload = None

        entries = payload.entry if payload else payload_dict.get("entry", [])

        for entry_obj in entries:
            changes = getattr(entry_obj, "changes", None) or (entry_obj.get("changes") if isinstance(entry_obj, dict) else [])
            for change in changes:
                value = getattr(change, "value", None) or (change.get("value") if isinstance(change, dict) else {})

                # Parse contacts
                contacts_map = {}
                contacts = getattr(value, "contacts", None) or (value.get("contacts") if isinstance(value, dict) else [])
                if contacts:
                    for contact in contacts:
                        wa_id = getattr(contact, "wa_id", None) or (contact.get("wa_id") if isinstance(contact, dict) else None)
                        profile = getattr(contact, "profile", None) or (contact.get("profile") if isinstance(contact, dict) else {})
                        name = getattr(profile, "name", None) or (profile.get("name") if isinstance(profile, dict) else None)
                        if wa_id:
                            contacts_map[wa_id] = name

                messages = getattr(value, "messages", None) or (value.get("messages") if isinstance(value, dict) else [])
                if not messages:
                    continue

                for msg in messages:
                    try:
                        sender_phone = getattr(msg, "from_", None) or (msg.get("from") if isinstance(msg, dict) else None)
                        normalized_sender_phone = None
                        if sender_phone:
                            try:
                                normalized_sender_phone = normalize_phone_number(sender_phone)
                            except PhoneNormalizationError:
                                normalized_sender_phone = sender_phone

                        msg_id = getattr(msg, "id", None) or (msg.get("id") if isinstance(msg, dict) else None)
                        raw_msg_type = getattr(msg, "type", None) or (msg.get("type") if isinstance(msg, dict) else "unknown")
                        msg_type = str(raw_msg_type).upper()

                        if msg_type not in ["TEXT", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT"]:
                            msg_type = "OTHER"

                        text_content = None
                        msg_text = getattr(msg, "text", None) or (msg.get("text") if isinstance(msg, dict) else None)
                        msg_image = getattr(msg, "image", None) or (msg.get("image") if isinstance(msg, dict) else None)

                        if msg_text:
                            text_content = getattr(msg_text, "body", None) or (msg_text.get("body") if isinstance(msg_text, dict) else None)
                        elif msg_image:
                            text_content = getattr(msg_image, "caption", None) or (msg_image.get("caption") if isinstance(msg_image, dict) else None)

                        # Timestamp integrity (R3-012)
                        # Do NOT silently overwrite event occurrence time with server receive time
                        server_received_at = datetime.now(timezone.utc)
                        raw_ts = getattr(msg, "timestamp", None) or (msg.get("timestamp") if isinstance(msg, dict) else None)
                        event_ts = None
                        timestamp_status = "VALID"

                        if raw_ts is not None and str(raw_ts).strip() != "":
                            try:
                                parsed_ts = datetime.fromtimestamp(int(raw_ts), tz=timezone.utc)
                                if abs((server_received_at - parsed_ts).total_seconds()) > 86400 * 365:
                                    timestamp_status = "ANOMALOUS_RANGE"
                                event_ts = parsed_ts
                            except Exception:
                                timestamp_status = "INVALID"
                                event_ts = None
                        else:
                            timestamp_status = "MISSING"
                            event_ts = None

                        customer_name = contacts_map.get(sender_phone) if sender_phone else None

                        universal_msg = UniversalMessage(
                            tenant_id=tenant_id,
                            channel="whatsapp",
                            external_message_id=msg_id,
                            direction="INBOUND",
                            message_type=msg_type,
                            text=text_content or (f"[{msg_type} message]" if msg_type != "TEXT" else ""),
                            timestamp=event_ts or server_received_at,  # UniversalMessage schema fallback
                            metadata={
                                "sender_phone": normalized_sender_phone or sender_phone,
                                "raw_sender_phone": sender_phone,
                                "sender_name": customer_name,
                                "raw_type": raw_msg_type,
                                "provider_timestamp": str(raw_ts) if raw_ts is not None else None,
                                "event_occurred_at": event_ts.isoformat() if event_ts else None,
                                "received_at": server_received_at.isoformat(),
                                "timestamp_status": timestamp_status,
                            },
                        )
                        universal_messages.append(universal_msg)
                    except Exception as item_err:
                        logger.error(f"Failed to process individual webhook message item safely: {item_err}")
                        continue

        return universal_messages
