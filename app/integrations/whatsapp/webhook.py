import logging
from fastapi import APIRouter, Depends, Request, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db_session

logger = logging.getLogger("integrations.whatsapp.webhook")

router = APIRouter(prefix="/integrations/whatsapp", tags=["WhatsApp Integration (Deprecated)"])


@router.post("/webhook", status_code=status.HTTP_200_OK, deprecated=True)
async def whatsapp_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Deprecated legacy endpoint. Delegates 100% directly to canonical `/api/v1/webhooks/whatsapp` receiver.
    Does NOT maintain an independent WhatsApp execution pipeline.
    """
    from app.api.v1.webhooks import receive_whatsapp_webhook
    logger.warning("Call to deprecated endpoint /integrations/whatsapp/webhook; delegating 100% to canonical /webhooks/whatsapp")
    return await receive_whatsapp_webhook(request=request, db=db)
