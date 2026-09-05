from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_id
from app.database.session import get_db_session
from app.repositories.domain import ConversationRepository
from app.schemas.domain import ConversationResponse, ConversationUpdate

router = APIRouter(prefix="/conversations", tags=["Conversations"])


def _get_tenant_id_or_400() -> UUID:
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant ID context missing or invalid.",
        )
    return tenant_id


@router.get("", response_model=list[ConversationResponse])
async def list_conversations(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = _get_tenant_id_or_400()
    repo = ConversationRepository(db)
    return await repo.list_all(tenant_id=tenant_id, skip=skip, limit=limit)


@router.get("/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID,
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = _get_tenant_id_or_400()
    repo = ConversationRepository(db)
    conversation = await repo.get_by_id(tenant_id=tenant_id, entity_id=conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    return conversation


@router.patch("/{conversation_id}", response_model=ConversationResponse)
async def update_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    db: AsyncSession = Depends(get_db_session),
):
    tenant_id = _get_tenant_id_or_400()
    repo = ConversationRepository(db)
    updated = await repo.update(
        tenant_id=tenant_id,
        entity_id=conversation_id,
        **payload.model_dump(exclude_unset=True),
    )
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found.",
        )
    await db.commit()
    return updated
