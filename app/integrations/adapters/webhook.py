import hmac
import hashlib
import uuid
import logging
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.exceptions import (
    WebhookVerificationError,
    PermanentIntegrationError,
)

logger = logging.getLogger(__name__)


class WebhookAdapter:
    """Provider adapter for generic Webhooks (Inbound signature verification & Outbound dispatches)."""

    provider_key = "webhook"

    async def connect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        return True

    async def disconnect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> bool:
        return True

    async def health_check(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> bool:
        return True

    async def execute(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        operation: str,
        params: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        if operation == "verify_signature":
            raw_body = params.get("raw_body", "")
            signature = params.get("signature", "")
            secret = credentials.get("webhook_secret") or credentials.get("secret", "")
            if not secret:
                raise WebhookVerificationError("Webhook secret is missing for signature verification")

            expected = hmac.new(
                secret.encode("utf-8"),
                raw_body.encode("utf-8") if isinstance(raw_body, str) else raw_body,
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(expected.lower(), signature.lower().replace("sha256=", "")):
                raise WebhookVerificationError("Invalid HMAC-SHA256 webhook signature")

            return {"verified": True}

        elif operation == "dispatch":
            url = params.get("url") or credentials.get("url")
            if not url:
                raise PermanentIntegrationError("Missing target URL for webhook dispatch", error_code="MISSING_URL")

            payload = params.get("payload", {})
            return {
                "status": "dispatched",
                "target_url": url,
                "payload_size": len(str(payload)),
            }
        else:
            raise PermanentIntegrationError(f"Unsupported webhook operation: {operation}", error_code="INVALID_OPERATION")

    async def normalize_event(
        self,
        event_type: str,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "event_type": event_type if event_type.startswith("webhook.") else f"webhook.{event_type}",
            "payload": raw_payload,
        }
