import logging
from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.integrations.whatsapp.parser import WhatsAppParser
from app.integrations.whatsapp.sender import WhatsAppSender
from app.core.router.router import MessageRouter
from app.repositories.domain import (
    CustomerRepository,
    ConversationRepository,
    MessageRepository,
)

logger = logging.getLogger("integrations.whatsapp.webhook")

router = APIRouter(prefix="/integrations/whatsapp", tags=["WhatsApp Integration"])


@router.post("/webhook", status_code=status.HTTP_200_OK)
async def whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """Webhook receiver endpoint for WhatsApp messages."""
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID context missing or invalid.",
        )

    try:
        body = await request.json()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body"
        )

    universal_messages = WhatsAppParser.parse_payload(tenant_id, body)
    if not universal_messages:
        return {"status": "ignored", "reason": "No messages found in payload"}

    customer_repo = CustomerRepository(db)
    conv_repo = ConversationRepository(db)
    msg_repo = MessageRepository(db)
    message_router = MessageRouter()
    sender = WhatsAppSender(is_development=True)

    processed_results = []

    for un_msg in universal_messages:
        if un_msg.external_message_id:
            existing_msg = await msg_repo.get_by_external_id(
                tenant_id, un_msg.external_message_id
            )
            if existing_msg:
                logger.info(
                    f"Duplicate webhook message {un_msg.external_message_id} ignored."
                )
                processed_results.append(
                    {"external_message_id": un_msg.external_message_id, "status": "duplicate"}
                )
                continue

        sender_phone = un_msg.metadata.get("sender_phone")
        sender_name = un_msg.metadata.get("sender_name") or "WhatsApp Customer"

        customer = None
        if sender_phone:
            customer = await customer_repo.get_by_phone(tenant_id, sender_phone)

        if not customer:
            customer = await customer_repo.create(
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

        if sender_phone:
            await sender.send_message(
                tenant_id=tenant_id,
                recipient_phone=sender_phone,
                message_text=route_result.response_text,
            )

        processed_results.append(
            {
                "external_message_id": un_msg.external_message_id,
                "status": "processed",
                "was_ai_called": route_result.was_ai_called,
            }
        )

    await db.commit()
    return {"status": "success", "processed": processed_results}
