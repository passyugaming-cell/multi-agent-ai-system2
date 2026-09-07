import uuid
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.repository import MemoryRepository
from app.memory.validators import MemoryValidator
from app.memory.schemas import (
    MemoryType,
    MemoryCreateSchema,
    MemoryUpdateSchema,
    MemoryItemSchema,
)


class ClientMemoryService:
    """Service managing tenant-isolated client memory items."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.repo = MemoryRepository(db_session)

    async def add_memory(
        self,
        tenant_id: uuid.UUID,
        create_data: MemoryCreateSchema,
    ) -> MemoryItemSchema:
        m_type, conf = MemoryValidator.validate_memory_type_source(
            create_data.memory_type, create_data.source, create_data.confidence
        )

        item = await self.repo.create_client_memory(
            tenant_id=tenant_id,
            key=create_data.key,
            memory_type=m_type.value,
            content=create_data.content,
            source=create_data.source,
            confidence=conf,
            importance=create_data.importance.value,
            expires_at=create_data.expires_at,
            meta_data=create_data.meta_data,
        )

        return MemoryItemSchema(
            id=item.id,
            tenant_id=item.tenant_id,
            is_business=False,
            memory_type=MemoryType(item.memory_type),
            key=item.key,
            content=item.content,
            source=item.source,
            confidence=item.confidence,
            status=item.status,
            importance=item.importance,
            version=item.version,
            expires_at=item.expires_at,
            last_verified_at=item.last_verified_at,
            meta_data=item.meta_data,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    async def get_memory_by_key(self, tenant_id: uuid.UUID, key: str) -> MemoryItemSchema | None:
        item = await self.repo.get_client_memory_by_key(tenant_id, key)
        if not item:
            return None
        return MemoryItemSchema(
            id=item.id,
            tenant_id=item.tenant_id,
            is_business=False,
            memory_type=MemoryType(item.memory_type),
            key=item.key,
            content=item.content,
            source=item.source,
            confidence=item.confidence,
            status=item.status,
            importance=item.importance,
            version=item.version,
            expires_at=item.expires_at,
            last_verified_at=item.last_verified_at,
            meta_data=item.meta_data,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )

    async def list_memories(
        self,
        tenant_id: uuid.UUID,
        memory_type: str | None = None,
        status: str = "ACTIVE",
        query_keywords: list[str] | None = None,
        customer_id: uuid.UUID | None = None,
    ) -> list[MemoryItemSchema]:
        items = await self.repo.list_client_memories(
            tenant_id=tenant_id,
            memory_type=memory_type,
            status=status,
            query_keywords=query_keywords,
            customer_id=customer_id,
        )
        return [
            MemoryItemSchema(
                id=item.id,
                tenant_id=item.tenant_id,
                is_business=False,
                memory_type=MemoryType(item.memory_type),
                key=item.key,
                content=item.content,
                source=item.source,
                confidence=item.confidence,
                status=item.status,
                importance=item.importance,
                version=item.version,
                expires_at=item.expires_at,
                last_verified_at=item.last_verified_at,
                meta_data=item.meta_data,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
            for item in items
        ]
