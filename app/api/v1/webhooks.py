import uuid
import json
import logging
import hmac
import hashlib
from typing import Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.integrations.service import IntegrationService
from app.integrations.events import publish_integration_event
from app.integrations.exceptions import WebhookVerificationError, IntegrationNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])

MAX_WEBHOOK_AGE_SECONDS = 300  # 5 minutes timestamp tolerance for replay protection


@router.post("/inbound/{provider}")
async def receive_inbound_webhook(
    provider: str,
    request: Request,
    x_tenant_id: str = Header(...),
    x_signature: str | None = Header(None, alias="X-Signature"),
    x_timestamp: str | None = Header(None, alias="X-Timestamp"),
    db: AsyncSession = Depends(get_db),
) -> Any:
    # 1. Resolve tenant context safely
    try:
        tenant_id = uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header must be a valid UUID",
        )

    # 2. Replay protection: check timestamp freshness if present
    if x_timestamp:
        try:
            ts = float(x_timestamp)
            now = datetime.now(timezone.utc).timestamp()
            if abs(now - ts) > MAX_WEBHOOK_AGE_SECONDS:
                logger.warning("Replayed or expired webhook request rejected for tenant %s provider %s", tenant_id, provider)
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Webhook timestamp is outside tolerance (replay protection)",
                )
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="X-Timestamp header must be a valid numeric unix timestamp",
            )

    # 3. Read raw payload
    raw_body = await request.body()
    try:
        body_str = raw_body.decode("utf-8")
        payload = json.loads(body_str)
    except Exception:
        body_str = str(raw_body)
        payload = {"raw_body": body_str}

    service = IntegrationService(db)

    # 4. Resolve WebhookConfig or Connection Secret securely for tenant
    webhook_secret = await service.get_webhook_secret(tenant_id, provider)
    if not webhook_secret:
        logger.warning("No active WebhookConfig or secret found for tenant %s provider %s", tenant_id, provider)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Webhook secret not configured for provider {provider}",
        )

    # 5. Mandatory signature verification prior to accepting/normalizing payload
    if not x_signature:
        logger.warning("Missing X-Signature header for tenant %s provider %s", tenant_id, provider)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing required X-Signature header",
        )

    expected_sig = hmac.new(
        webhook_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    clean_sig = x_signature.lower().replace("sha256=", "").strip()
    if not hmac.compare_digest(expected_sig.lower(), clean_sig):
        logger.warning("Invalid HMAC-SHA256 webhook signature for tenant %s provider %s", tenant_id, provider)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid HMAC-SHA256 webhook signature",
        )

    # 6. Normalize event payload & publish to Phase 2 EventBus
    normalized = {
        "event_type": f"webhook.{provider}.received",
        "payload": payload,
        "verified": True,
    }

    await publish_integration_event(
        tenant_id=tenant_id,
        event_type="webhook.received",
        payload=normalized,
        source=f"webhook_{provider}",
    )

    return {"status": "accepted", "provider": provider}
