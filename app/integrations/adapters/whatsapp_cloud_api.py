import hmac
import hashlib
import logging
from typing import Any
import uuid
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.interfaces import IntegrationAdapter
from app.integrations.exceptions import (
    PermanentIntegrationError,
    TransientIntegrationError,
    IntegrationError,
)

logger = logging.getLogger(__name__)

META_GRAPH_API_VERSION = "v18.0"
GRAPH_BASE_URL = f"https://graph.facebook.com/{META_GRAPH_API_VERSION}"


class WhatsAppCloudApiAdapter(IntegrationAdapter):
    """
    Official Meta WhatsApp Cloud API Channel Adapter.
    Provides outbound messaging, webhook signature verification, and payload normalization.
    """

    provider_key: str = "whatsapp_cloud_api"

    def __init__(self, is_development: bool = False) -> None:
        self.is_development = is_development

    async def connect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        """Validates credentials required for WhatsApp Cloud API integration."""
        phone_number_id = credentials.get("phone_number_id")
        access_token = credentials.get("access_token")

        if not phone_number_id or not access_token:
            raise PermanentIntegrationError(
                "WhatsApp Cloud API requires 'phone_number_id' and 'access_token'.",
                error_code="AUTHENTICATION_ERROR",
            )
        return True

    async def disconnect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> bool:
        """Disconnects the adapter connection."""
        return True

    async def health_check(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> bool:
        """Checks API connectivity and token validity against Meta Graph API."""
        phone_number_id = credentials.get("phone_number_id")
        access_token = credentials.get("access_token")

        if not phone_number_id or not access_token:
            return False

        if self.is_development or access_token.startswith("mock_") or access_token.startswith("sim_"):
            return True

        endpoint = f"{GRAPH_BASE_URL}/{phone_number_id}"
        headers = {"Authorization": f"Bearer {access_token}"}

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(endpoint, headers=headers)
                return resp.status_code == 200
        except Exception as exc:
            logger.warning("WhatsApp health check failed for tenant %s: %s", tenant_id, exc)
            return False

    async def execute(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        operation: str,
        params: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        """Executes WhatsApp Cloud API operations deterministically."""
        access_token = credentials.get("access_token")
        phone_number_id = credentials.get("phone_number_id")

        if not access_token or not phone_number_id:
            raise PermanentIntegrationError(
                "Missing 'access_token' or 'phone_number_id' in connection credentials.",
                error_code="AUTHENTICATION_ERROR",
            )

        if operation in ("send_message", "send_text", "send_media", "send_template"):
            return await self._send_outbound_message(phone_number_id, access_token, params)
        elif operation == "get_connection_status":
            return {
                "tenant_id": str(tenant_id),
                "connection_id": str(connection_id),
                "phone_number_id": phone_number_id,
                "provider": self.provider_key,
                "status": "ACTIVE",
            }
        else:
            raise PermanentIntegrationError(
                f"Unsupported WhatsApp operation: {operation}",
                error_code="INVALID_OPERATION",
            )

    async def _send_outbound_message(
        self,
        phone_number_id: str,
        access_token: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        recipient = params.get("recipient") or params.get("to") or params.get("recipient_phone")
        if not recipient:
            raise PermanentIntegrationError(
                "Outbound message requires recipient phone number.",
                error_code="VALIDATION_ERROR",
            )

        recipient_clean = "".join(filter(str.isdigit, str(recipient)))

        msg_type = params.get("message_type") or params.get("type") or "text"
        text_body = params.get("text") or params.get("body") or params.get("message")
        media_url = params.get("media_url") or params.get("url")
        template_name = params.get("template_name")
        language_code = params.get("language_code", "id")

        payload: dict[str, Any] = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": recipient_clean,
        }

        if template_name:
            payload["type"] = "template"
            payload["template"] = {
                "name": template_name,
                "language": {"code": language_code},
            }
            if "components" in params:
                payload["template"]["components"] = params["components"]
        elif msg_type.lower() in ("image", "video", "audio", "document") and media_url:
            payload["type"] = msg_type.lower()
            media_obj: dict[str, Any] = {"link": media_url}
            if text_body and msg_type.lower() in ("image", "video", "document"):
                media_obj["caption"] = text_body
            payload[msg_type.lower()] = media_obj
        else:
            payload["type"] = "text"
            payload["text"] = {"preview_url": False, "body": text_body or ""}

        if self.is_development or access_token.startswith("mock_") or access_token.startswith("sim_"):
            logger.info("[SIMULATED WHATSAPP OUTBOUND] To: %s | Type: %s", recipient_clean, payload.get("type"))
            sim_id = f"wamid.sim_{uuid.uuid4().hex[:16]}"
            return {
                "success": True,
                "messaging_product": "whatsapp",
                "contacts": [{"input": recipient_clean, "wa_id": recipient_clean}],
                "messages": [{"id": sim_id}],
                "provider_message_id": sim_id,
                "simulated": True,
            }

        endpoint = f"{GRAPH_BASE_URL}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(endpoint, json=payload, headers=headers)
                if resp.status_code in (200, 201):
                    data = resp.json()
                    msg_id = data.get("messages", [{}])[0].get("id")
                    return {
                        "success": True,
                        "messaging_product": "whatsapp",
                        "contacts": data.get("contacts", []),
                        "messages": data.get("messages", []),
                        "provider_message_id": msg_id,
                        "raw_response": data,
                    }
                elif resp.status_code in (429, 500, 502, 503, 504):
                    data = resp.json() if resp.content else {}
                    err_msg = data.get("error", {}).get("message") or f"HTTP {resp.status_code}"
                    raise TransientIntegrationError(
                        f"WhatsApp Cloud API retryable error: {err_msg}",
                        error_code="RATE_LIMIT_OR_TIMEOUT",
                    )
                else:
                    data = resp.json() if resp.content else {}
                    err_msg = data.get("error", {}).get("message") or f"HTTP {resp.status_code}"
                    raise PermanentIntegrationError(
                        f"WhatsApp Cloud API error: {err_msg}",
                        error_code="PROVIDER_ERROR",
                    )
        except (TransientIntegrationError, PermanentIntegrationError):
            raise
        except Exception as exc:
            logger.error("WhatsApp Cloud API network exception: %s", exc)
            raise TransientIntegrationError(
                f"Network failure reaching WhatsApp Cloud API: {exc}",
                error_code="NETWORK_ERROR",
            )

    def verify_webhook_signature(
        self,
        raw_body: bytes,
        signature_header: str | None,
        app_secret: str,
    ) -> bool:
        if not signature_header or not app_secret:
            return False

        clean_sig = signature_header.lower().replace("sha256=", "").strip()
        expected_sig = hmac.new(
            app_secret.encode("utf-8"),
            raw_body,
            hashlib.sha256,
        ).hexdigest().lower()

        return hmac.compare_digest(expected_sig, clean_sig)

    def verify_handshake(
        self,
        mode: str | None,
        challenge: str | None,
        verify_token: str | None,
        expected_token: str,
    ) -> str | None:
        if mode == "subscribe" and verify_token and hmac.compare_digest(verify_token, expected_token):
            return challenge
        return None

    async def normalize_event(
        self,
        event_type: str,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "event_type": event_type,
            "channel": "whatsapp",
            "provider": self.provider_key,
            "raw_payload": raw_payload,
        }
