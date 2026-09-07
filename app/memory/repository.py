import uuid
from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import BusinessMemory, ClientMemory, MemoryChangeProposal
from app.memory.schemas import (
    MemoryType,
    MemoryStatus,
    MemoryCreateSchema,
    MemoryUpdateSchema,
    MemoryChangeProposalSchema,
    MemoryScope,
)
from app.core.exceptions import AppError


class MemoryRepository:
    """Async SQLAlchemy repository for Business Memory, Client Memory, and Proposals."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    # --- Business Memory Operations ---

    async def create_business_memory(
        self,
        tenant_id: uuid.UUID | None,
        key: str,
        memory_type: str,
        content: dict,
        source: str = "system",
        confidence: float = 1.0,
        importance: str = "NORMAL",
        is_platform_wide: bool = False,
        expires_at: datetime | None = None,
        meta_data: dict | None = None,
    ) -> BusinessMemory:
        item = BusinessMemory(
            tenant_id=tenant_id,
            is_platform_wide=is_platform_wide,
            key=key,
            memory_type=memory_type,
            content=content,
            source=source,
            confidence=confidence,
            importance=importance,
            status="ACTIVE",
            version=1,
            last_verified_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            meta_data=meta_data,
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def get_business_memory(self, item_id: uuid.UUID) -> BusinessMemory | None:
        stmt = select(BusinessMemory).where(BusinessMemory.id == item_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def get_business_memory_by_key(self, tenant_id: uuid.UUID | None, key: str) -> BusinessMemory | None:
        filters = [BusinessMemory.key == key, BusinessMemory.status == "ACTIVE"]
        if tenant_id:
            filters.append(or_(BusinessMemory.tenant_id == tenant_id, BusinessMemory.is_platform_wide == True))
        stmt = select(BusinessMemory).where(and_(*filters)).order_by(BusinessMemory.version.desc())
        return (await self.session.execute(stmt)).scalars().first()

    async def list_business_memories(
        self,
        tenant_id: uuid.UUID | None = None,
        memory_type: str | None = None,
        status: str = "ACTIVE",
        query_keywords: list[str] | None = None,
    ) -> Sequence[BusinessMemory]:
        filters = []
        if status:
            filters.append(BusinessMemory.status == status)
        if memory_type:
            filters.append(BusinessMemory.memory_type == memory_type)

        if tenant_id:
            filters.append(or_(BusinessMemory.tenant_id == tenant_id, BusinessMemory.is_platform_wide == True))

        stmt = select(BusinessMemory).where(and_(*filters)).order_by(BusinessMemory.updated_at.desc())
        items = (await self.session.execute(stmt)).scalars().all()

        if query_keywords:
            # Filter in Python by key or content matching
            filtered = []
            for item in items:
                key_text = item.key.lower()
                content_text = str(item.content).lower()
                if any(kw.lower() in key_text or kw.lower() in content_text for kw in query_keywords):
                    filtered.append(item)
            return filtered

        return items

    async def update_business_memory(
        self,
        item_id: uuid.UUID,
        update_data: dict,
    ) -> BusinessMemory:
        item = await self.get_business_memory(item_id)
        if not item:
            raise AppError("Business memory item not found.", status_code=404)

        if "content" in update_data and update_data["content"] is not None:
            item.content = update_data["content"]
            item.version += 1

        for field in ("memory_type", "source", "confidence", "status", "importance", "expires_at", "meta_data"):
            if field in update_data and update_data[field] is not None:
                setattr(item, field, update_data[field])

        item.last_verified_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    # --- Client Memory Operations (Tenant Isolated) ---

    async def create_client_memory(
        self,
        tenant_id: uuid.UUID,
        key: str,
        memory_type: str,
        content: dict,
        source: str = "system",
        confidence: float = 1.0,
        importance: str = "NORMAL",
        expires_at: datetime | None = None,
        meta_data: dict | None = None,
    ) -> ClientMemory:
        item = ClientMemory(
            tenant_id=tenant_id,
            key=key,
            memory_type=memory_type,
            content=content,
            source=source,
            confidence=confidence,
            importance=importance,
            status="ACTIVE",
            version=1,
            last_verified_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            meta_data=meta_data,
        )
        self.session.add(item)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    async def get_client_memory_by_key(self, tenant_id: uuid.UUID, key: str) -> ClientMemory | None:
        stmt = select(ClientMemory).where(
            and_(ClientMemory.tenant_id == tenant_id, ClientMemory.key == key, ClientMemory.status == "ACTIVE")
        )
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_client_memories(
        self,
        tenant_id: uuid.UUID,
        memory_type: str | None = None,
        status: str = "ACTIVE",
        query_keywords: list[str] | None = None,
        customer_id: uuid.UUID | None = None,
    ) -> Sequence[ClientMemory]:
        filters = [ClientMemory.tenant_id == tenant_id]
        if status:
            filters.append(ClientMemory.status == status)
        if memory_type:
            filters.append(ClientMemory.memory_type == memory_type)

        stmt = select(ClientMemory).where(and_(*filters)).order_by(ClientMemory.updated_at.desc())
        items = (await self.session.execute(stmt)).scalars().all()

        # Customer isolation filtering
        customer_filtered = []
        for item in items:
            item_customer_id = (item.meta_data or {}).get("customer_id") if item.meta_data else None
            if customer_id is not None:
                # If customer_id provided, include if item matches this customer or is unassigned tenant-level memory
                if item_customer_id == str(customer_id) or item_customer_id is None:
                    customer_filtered.append(item)
            else:
                # If no customer_id provided, ONLY include tenant-level memory without a specific customer_id
                if item_customer_id is None:
                    customer_filtered.append(item)

        items = customer_filtered

        if query_keywords:
            filtered = []
            for item in items:
                key_text = item.key.lower()
                content_text = str(item.content).lower()
                if any(kw.lower() in key_text or kw.lower() in content_text for kw in query_keywords):
                    filtered.append(item)
            return filtered

        return items

    async def update_client_memory(
        self,
        tenant_id: uuid.UUID,
        key: str,
        update_data: dict,
    ) -> ClientMemory:
        item = await self.get_client_memory_by_key(tenant_id, key)
        if not item:
            raise AppError(f"Client memory item '{key}' not found for tenant.", status_code=404)

        if "content" in update_data and update_data["content"] is not None:
            item.content = update_data["content"]
            item.version += 1

        for field in ("memory_type", "source", "confidence", "status", "importance", "expires_at", "meta_data"):
            if field in update_data and update_data[field] is not None:
                setattr(item, field, update_data[field])

        item.last_verified_at = datetime.now(timezone.utc)
        await self.session.commit()
        await self.session.refresh(item)
        return item

    # --- Proposal Operations ---

    async def create_proposal(
        self,
        tenant_id: uuid.UUID | None,
        memory_scope: str,
        proposed_key: str,
        proposed_type: str,
        proposed_content: dict,
        reason: str,
        source_agent: str,
        approval_id: uuid.UUID | None = None,
    ) -> MemoryChangeProposal:
        proposal = MemoryChangeProposal(
            tenant_id=tenant_id,
            memory_scope=memory_scope,
            proposed_key=proposed_key,
            proposed_type=proposed_type,
            proposed_content=proposed_content,
            reason=reason,
            source_agent=source_agent,
            status="PENDING",
            approval_id=approval_id,
        )
        self.session.add(proposal)
        await self.session.commit()
        await self.session.refresh(proposal)
        return proposal

    async def get_proposal(self, proposal_id: uuid.UUID) -> MemoryChangeProposal | None:
        stmt = select(MemoryChangeProposal).where(MemoryChangeProposal.id == proposal_id)
        return (await self.session.execute(stmt)).scalar_one_or_none()

    async def list_proposals(self, tenant_id: uuid.UUID | None = None, status: str = "PENDING") -> Sequence[MemoryChangeProposal]:
        filters = [MemoryChangeProposal.status == status] if status else []
        if tenant_id:
            filters.append(MemoryChangeProposal.tenant_id == tenant_id)

        stmt = select(MemoryChangeProposal).where(and_(*filters)).order_by(MemoryChangeProposal.created_at.desc())
        return (await self.session.execute(stmt)).scalars().all()
