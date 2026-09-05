import uuid
import json
import logging
import hmac
import hashlib
from typing import Any
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Header, Request, status
from fastapi.responses import Response, PlainTextResponse
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.database.models.integrations import Integration, IntegrationConnection, IntegrationCredential, IntegrationExecution
from app.integrations.service import IntegrationService
from app.integrations.adapters.whatsapp_cloud_api import WhatsAppCloudApiAdapter
from app.integrations.whatsapp.parser import WhatsAppParser
from app.integrations.events import publish_integration_event
from app.integrations.exceptions import WebhookVerificationError, IntegrationNotFoundError
from app.core.router.router import MessageRouter
from app.repositories.domain import CustomerRepository, ConversationRepository, MessageRepository

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
    try:
        tenant_id = uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header must be a valid UUID",
        )

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

    raw_body = await request.body()
    try:
        body_str = raw_body.decode("utf-8")
        payload = json.loads(body_str)
    except Exception:
        body_str = str(raw_body)
        payload = {"raw_body": body_str}

    service = IntegrationService(db)

    webhook_secret = await service.get_webhook_secret(tenant_id, provider)
    if not webhook_secret:
        logger.warning("No active WebhookConfig or secret found for tenant %s provider %s", tenant_id, provider)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Webhook secret not configured for provider {provider}",
        )

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

    idempotency_key = f"midtrans_webhook_{transaction_id}_{payload.get('transaction_status')}"
    existing_exec = await service.idempotency.get_existing_execution(tenant_id, idempotency_key)
    if existing_exec:
        return {"status": "PROCESSED", "idempotent": True, "transaction_status": norm_status}

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


@router.get("/whatsapp")
async def verify_whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Response:
    """
    WhatsApp Webhook Verification Handshake (GET).
    Validates hub.mode, hub.challenge, and hub.verify_token against stored connection credentials.
    """
    params = request.query_params
    mode = params.get("hub.mode")
    challenge = params.get("hub.challenge")
    verify_token = params.get("hub.verify_token")

    if mode != "subscribe" or not verify_token or not challenge:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid verification parameters",
        )

    stmt = (
        select(IntegrationConnection)
        .join(Integration, IntegrationConnection.integration_id == Integration.id)
        .where(
            and_(
                IntegrationConnection.status.in_(["ACTIVE", "CONNECTED"]),
                Integration.provider_key.in_(["whatsapp_cloud_api", "whatsapp"]),
            )
        )
    )
    connections = (await db.execute(stmt)).scalars().all()
    service = IntegrationService(db)
    adapter = WhatsAppCloudApiAdapter()

    for conn in connections:
        c_stmt = select(IntegrationCredential).where(
            and_(
                IntegrationCredential.tenant_id == conn.tenant_id,
                IntegrationCredential.connection_id == conn.id,
                IntegrationCredential.revoked_at == None,
            )
        )
        cred = (await db.execute(c_stmt)).scalar_one_or_none()
        if not cred:
            continue
        creds = service.vault.decrypt_credentials(cred.encrypted_secret)
        expected_token = creds.get("verify_token") or creds.get("webhook_secret") or creds.get("secret")
        if expected_token:
            result = adapter.verify_handshake(mode, challenge, verify_token, expected_token)
            if result is not None:
                return Response(content=result, media_type="text/plain", status_code=200)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Webhook verification failed: invalid verify_token",
    )


@router.post("/whatsapp")
async def receive_whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Official WhatsApp Webhook Endpoint (POST).
    1. Parses raw JSON.
    2. Derives tenant_id strictly from active IntegrationConnection matching phone_number_id.
    3. Verifies X-Hub-Signature-256 using stored app_secret in constant time.
    4. Enforces idempotency on messages and status updates.
    5. Normalizes messages and status events, creating/updating Universal Message, Customer, and Conversation.
    6. Routes inbound messages via MessageRouter and executes outbound reply via adapter.
    7. Emits EventBus events.
    """
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON payload")

    phone_number_id = None
    entries = payload.get("entry", [])
    for entry in entries:
        for change in entry.get("changes", []):
            val = change.get("value", {})
            metadata = val.get("metadata", {})
            if metadata.get("phone_number_id"):
                phone_number_id = metadata.get("phone_number_id")
                break
        if phone_number_id:
            break

    if not phone_number_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="phone_number_id missing from webhook payload",
        )

    service = IntegrationService(db)
    stmt = (
        select(IntegrationConnection)
        .join(Integration, IntegrationConnection.integration_id == Integration.id)
        .where(
            and_(
                IntegrationConnection.status.in_(["ACTIVE", "CONNECTED"]),
                Integration.provider_key.in_(["whatsapp_cloud_api", "whatsapp"]),
            )
        )
    )
    connections = (await db.execute(stmt)).scalars().all()

    target_connection = None
    target_credentials = None

    for conn in connections:
        if conn.external_account_id == phone_number_id:
            target_connection = conn
            c_stmt = select(IntegrationCredential).where(
                and_(
                    IntegrationCredential.tenant_id == conn.tenant_id,
                    IntegrationCredential.connection_id == conn.id,
                    IntegrationCredential.revoked_at == None,
                )
            )
            cred = (await db.execute(c_stmt)).scalar_one_or_none()
            if cred:
                target_credentials = service.vault.decrypt_credentials(cred.encrypted_secret)
            break

    if not target_connection:
        for conn in connections:
            c_stmt = select(IntegrationCredential).where(
                and_(
                    IntegrationCredential.tenant_id == conn.tenant_id,
                    IntegrationCredential.connection_id == conn.id,
                    IntegrationCredential.revoked_at == None,
                )
            )
            cred = (await db.execute(c_stmt)).scalar_one_or_none()
            if cred:
                creds = service.vault.decrypt_credentials(cred.encrypted_secret)
                if creds.get("phone_number_id") == phone_number_id:
                    target_connection = conn
                    target_credentials = creds
                    break

    if not target_connection or not target_credentials:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active WhatsApp connection mapped to phone_number_id '{phone_number_id}'",
        )

    tenant_id = target_connection.tenant_id
    app_secret = target_credentials.get("app_secret") or target_credentials.get("secret")

    x_signature = request.headers.get("X-Hub-Signature-256") or request.headers.get("X-Signature")
    adapter = WhatsAppCloudApiAdapter()
    if app_secret:
        if not x_signature or not adapter.verify_webhook_signature(raw_body, x_signature, app_secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or missing X-Hub-Signature-256 signature",
            )

    processed_results = []
    msg_repo = MessageRepository(db)
    cust_repo = CustomerRepository(db)
    conv_repo = ConversationRepository(db)
    message_router = MessageRouter()

    for entry in entries:
        for change in entry.get("changes", []):
            val = change.get("value", {})

            messages_list = val.get("messages", [])
            if messages_list:
                universal_messages = WhatsAppParser.parse_payload(tenant_id, payload)
                for un_msg in universal_messages:
                    if un_msg.external_message_id:
                        existing_msg = await msg_repo.get_by_external_id(tenant_id, un_msg.external_message_id)
                        if existing_msg:
                            processed_results.append({
                                "external_message_id": un_msg.external_message_id,
                                "status": "duplicate",
                            })
                            continue

                    sender_phone = un_msg.metadata.get("sender_phone")
                    sender_name = un_msg.metadata.get("sender_name") or "WhatsApp Customer"

                    customer = None
                    if sender_phone:
                        customer = await cust_repo.get_by_phone(tenant_id, sender_phone)

                    if not customer:
                        customer = await cust_repo.create(
                            tenant_id=tenant_id,
                            name=sender_name,
                            phone=sender_phone,
                            external_id=sender_phone,
                        )

                    conversation = await conv_repo.get_active_by_customer(tenant_id, customer.id)
                    if not conversation:
                        conversation = await conv_repo.create(
                            tenant_id=tenant_id,
                            customer_id=customer.id,
                            channel="whatsapp",
                            status="OPEN",
                        )

                    inbound_db_msg = await msg_repo.create(
                        tenant_id=tenant_id,
                        conversation_id=conversation.id,
                        direction="INBOUND",
                        message_type=un_msg.message_type,
                        text=un_msg.text,
                        external_message_id=un_msg.external_message_id,
                        metadata_=un_msg.metadata,
                    )

                    route_result = await message_router.route_message(
                        tenant_id=tenant_id,
                        conversation=conversation,
                        message=inbound_db_msg,
                        session=db,
                    )

                    outbound_db_msg = await msg_repo.create(
                        tenant_id=tenant_id,
                        conversation_id=conversation.id,
                        direction="OUTBOUND",
                        message_type="TEXT",
                        text=route_result.response_text,
                    )

                    if sender_phone and not conversation.human_handoff:
                        try:
                            await service.execute_operation(
                                tenant_id=tenant_id,
                                connection_id=target_connection.id,
                                operation="send_message",
                                params={"recipient_phone": sender_phone, "text": route_result.response_text},
                            )
                        except Exception as send_err:
                            logger.error("Failed to send WhatsApp response via adapter: %s", send_err)

                    await publish_integration_event(
                        tenant_id=tenant_id,
                        event_type="whatsapp.message_received",
                        payload={
                            "external_message_id": un_msg.external_message_id,
                            "customer_id": str(customer.id),
                            "conversation_id": str(conversation.id),
                            "message_type": un_msg.message_type,
                            "text": un_msg.text,
                        },
                    )

                    processed_results.append({
                        "external_message_id": un_msg.external_message_id,
                        "status": "processed",
                        "was_ai_called": route_result.was_ai_called,
                    })

            statuses = val.get("statuses", [])
            for st in statuses:
                status_id = st.get("id")
                status_val = st.get("status", "").lower()
                idempotency_key = f"wa_status_{status_id}_{status_val}"

                existing_exec = await service.idempotency.get_existing_execution(tenant_id, idempotency_key)
                if existing_exec:
                    processed_results.append({"status_id": status_id, "status": "duplicate_event"})
                    continue

                if status_id:
                    existing_msg = await msg_repo.get_by_external_id(tenant_id, status_id)
                    if existing_msg:
                        meta = dict(existing_msg.metadata_ or {})
                        meta["delivery_status"] = status_val
                        meta["status_timestamp"] = st.get("timestamp")
                        existing_msg.metadata_ = meta

                exec_rec = IntegrationExecution(
                    tenant_id=tenant_id,
                    connection_id=target_connection.id,
                    operation=f"status_{status_val}",
                    status="COMPLETED",
                    idempotency_key=idempotency_key,
                    started_at=datetime.now(timezone.utc),
                    completed_at=datetime.now(timezone.utc),
                    response_payload={"status": status_val, "status_id": status_id},
                )
                db.add(exec_rec)

                await publish_integration_event(
                    tenant_id=tenant_id,
                    event_type=f"whatsapp.message_{status_val}",
                    payload={
                        "status_id": status_id,
                        "status": status_val,
                        "recipient_id": st.get("recipient_id"),
                    },
                    idempotency_key=idempotency_key,
                )

                processed_results.append({"status_id": status_id, "status": status_val})

    await db.commit()
    return {"status": "success", "tenant_id": str(tenant_id), "processed": processed_results}
