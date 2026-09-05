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


@router.post("/midtrans")
async def receive_midtrans_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Dedicated Midtrans Webhook Endpoint.
    1. Parses raw JSON.
    2. Derives tenant_id strictly from internal Invoice record matching order_id.
    3. Verifies SHA-512 signature using connection's server_key with constant-time comparison.
    4. Enforces idempotency.
    5. Normalizes status and updates Invoice/Payment billing state.
    6. Emits EventBus events and executes workflows where appropriate.
    """
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    order_id_str = payload.get("order_id")
    if not order_id_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="order_id is required in webhook payload")

    try:
        invoice_id = uuid.UUID(order_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid order_id format")

    from sqlalchemy import select
    from app.database.models.billing import Invoice
    stmt = select(Invoice).where(Invoice.id == invoice_id)
    invoice = (await db.execute(stmt)).scalar_one_or_none()
    if not invoice:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Internal Invoice record not found for order_id")

    tenant_id = invoice.tenant_id

    service = IntegrationService(db)
    conn = await service.get_connection_by_provider(tenant_id, "midtrans")
    if not conn:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Midtrans integration connection not found for tenant")

    from app.database.models.integrations import IntegrationCredential
    c_stmt = select(IntegrationCredential).where(
        IntegrationCredential.tenant_id == tenant_id,
        IntegrationCredential.connection_id == conn.id,
        IntegrationCredential.revoked_at == None,
    )
    cred = (await db.execute(c_stmt)).scalar_one_or_none()
    if not cred:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Midtrans credentials not found")

    creds = service.vault.decrypt_credentials(cred.encrypted_secret)
    server_key = creds.get("server_key")
    if not server_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Server key missing")

    from app.integrations.adapters.midtrans import MidtransAdapter
    adapter = MidtransAdapter()
    if not adapter.verify_notification(payload, server_key):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid SHA-512 signature_key")

    transaction_id = payload.get("transaction_id") or order_id_str
    norm_status = adapter.normalize_notification(payload)

    # Idempotency check via IntegrationIdempotencyChecker
    idempotency_key = f"midtrans_webhook_{transaction_id}_{payload.get('transaction_status')}"
    existing_exec = await service.idempotency.get_existing_execution(tenant_id, idempotency_key)
    if existing_exec:
        return {"status": "PROCESSED", "idempotent": True, "transaction_status": norm_status}

    # Update Payment/Invoice billing state
    from app.billing.payments import PaymentService
    pay_service = PaymentService(db)

    from app.database.models.billing import Payment
    p_stmt = select(Payment).where(Payment.tenant_id == tenant_id, Payment.invoice_id == invoice_id)
    payment = (await db.execute(p_stmt)).scalars().first()

    if not payment:
        payment = await pay_service.create_payment_intent(
            tenant_id=tenant_id,
            invoice_id=invoice_id,
            amount=invoice.total,
        )

    if norm_status == "SUCCEEDED" and payment.status != "SUCCEEDED":
        await pay_service.confirm_payment_success(
            tenant_id=tenant_id,
            payment_id=payment.id,
            provider_payment_id=transaction_id,
        )
    elif norm_status == "FAILED" and payment.status != "FAILED":
        await pay_service.record_payment_failure(
            tenant_id=tenant_id,
            payment_id=payment.id,
            reason=payload.get("status_message") or "Midtrans payment failed",
        )
    elif norm_status == "CANCELLED" and payment.status != "CANCELLED":
        payment.status = "CANCELLED"
        await db.commit()
    elif norm_status == "EXPIRED" and payment.status != "EXPIRED":
        payment.status = "EXPIRED"
        await db.commit()
    elif norm_status == "REFUNDED" and payment.status != "REFUNDED":
        payment.status = "REFUNDED"
        await db.commit()

    # Save idempotency record
    from app.database.models.integrations import IntegrationExecution
    exec_record = IntegrationExecution(
        tenant_id=tenant_id,
        connection_id=conn.id,
        operation="webhook_notification",
        status="COMPLETED",
        idempotency_key=idempotency_key,
        started_at=datetime.now(timezone.utc),
        completed_at=datetime.now(timezone.utc),
        response_payload={"normalized_status": norm_status},
    )
    db.add(exec_record)
    await db.commit()

    # Publish EventBus event
    await publish_integration_event(
        tenant_id=tenant_id,
        event_type=f"payment.midtrans.{norm_status.lower()}",
        payload={
            "invoice_id": str(invoice_id),
            "payment_id": str(payment.id),
            "transaction_id": transaction_id,
            "status": norm_status,
            "gross_amount": str(payload.get("gross_amount", "0")),
        },
        idempotency_key=idempotency_key,
    )

    return {"status": "PROCESSED", "normalized_status": norm_status, "invoice_id": str(invoice_id)}
