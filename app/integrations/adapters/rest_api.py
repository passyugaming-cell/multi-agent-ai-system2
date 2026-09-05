import uuid
import logging
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.exceptions import (
    PermanentIntegrationError,
)

logger = logging.getLogger(__name__)


class RestApiAdapter:
    """Provider adapter for generic REST API integrations."""

    provider_key = "rest_api"

    async def connect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        api_key = credentials.get("api_key") or credentials.get("bearer_token")
        if not api_key:
            raise PermanentIntegrationError("REST API connection requires api_key or bearer_token", error_code="INVALID_CREDENTIALS")
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
        return bool(credentials.get("api_key") or credentials.get("bearer_token"))

    async def execute(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        operation: str,
        params: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        api_key = credentials.get("api_key") or credentials.get("bearer_token")
        if not api_key:
            raise PermanentIntegrationError("Missing API key or token", error_code="UNAUTHORIZED")

        if operation == "ping":
            return {"status": "ok", "provider": "rest_api", "tenant_id": str(tenant_id)}
        elif operation == "http_request":
            method = params.get("method", "GET").upper()
            endpoint = params.get("endpoint", "/")
            return {
                "status": "success",
                "method": method,
                "endpoint": endpoint,
                "data": params.get("payload", {}),
            }
        else:
            raise PermanentIntegrationError(f"Unsupported REST API operation: {operation}", error_code="INVALID_OPERATION")

    async def normalize_event(
        self,
        event_type: str,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "event_type": f"rest_api.{event_type}",
            "data": raw_payload,
        }
