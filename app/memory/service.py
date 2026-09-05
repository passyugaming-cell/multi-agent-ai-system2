import uuid
from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy.ext.asyncio import AsyncSession

from app.memory.repository import MemoryRepository
from app.memory.business_memory import BusinessMemoryService
from app.memory.client_memory import ClientMemoryService
from app.memory.validators import MemoryValidator
from app.memory.schemas import (
    MemoryType,
    MemoryScope,
    MemoryStatus,
    MemoryCreateSchema,
    MemoryUpdateSchema,
    MemoryItemSchema,
    MemoryChangeProposalSchema,
    MemoryContextSchema,
)
from app.database.models.memory import MemoryChangeProposal
from app.core.exceptions import AppError


class MemoryService:
    """Unified Memory Service orchestrating Business Memory, Client Memory, Proposals, and Context Retrieval."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session
        self.repo = MemoryRepository(db_session)
        self.business_mem = BusinessMemoryService(db_session)
        self.client_mem = ClientMemoryService(db_session)

    async def get_relevant_context(
        self,
        tenant_id: uuid.UUID,
        objective: str,
        keywords: list[str] | None = None,
    ) -> MemoryContextSchema:
        """Retrieves only contextually relevant business and client memories without exposing unrelated data."""
        # Extract keywords from objective if none provided
        if not keywords:
            keywords = [w.strip() for w in objective.lower().split() if len(w) > 3]

        biz_items = await self.business_mem.list_memories(
            tenant_id=tenant_id,
            status="ACTIVE",
            query_keywords=keywords[:5] if keywords else None,
        )

        cli_items = await self.client_mem.list_memories(
            tenant_id=tenant_id,
            status="ACTIVE",
            query_keywords=keywords[:5] if keywords else None,
        )

        # Mark expired memories as OUTDATED on read
        now = datetime.now(timezone.utc)
        active_biz = []
        for item in biz_items:
            if item.expires_at and item.expires_at < now:
                await self.repo.update_business_memory(item.id, {"status": "OUTDATED"})
            else:
                active_biz.append(item)

        active_cli = []
        for item in cli_items:
            if item.expires_at and item.expires_at < now:
                await self.repo.update_client_memory(tenant_id, item.key, {"status": "OUTDATED"})
            else:
                active_cli.append(item)

        return MemoryContextSchema(
            tenant_id=tenant_id,
            business_memories=active_biz[:10],
            client_memories=active_cli[:10],
            retrieved_at=now,
        )

    async def save_memory_or_propose(
        self,
        scope: MemoryScope,
        tenant_id: uuid.UUID | None,
        create_data: MemoryCreateSchema,
        source_agent: str,
    ) -> tuple[MemoryItemSchema | None, MemoryChangeProposalSchema | None]:
        """Saves memory directly if permitted, or creates MemoryChangeProposal if approval is required."""
        requires_approval = MemoryValidator.requires_approval_for_change(
            scope, create_data.key, create_data.memory_type, create_data.source
        )

        if requires_approval:
            proposal = await self.repo.create_proposal(
                tenant_id=tenant_id,
                memory_scope=scope.value,
                proposed_key=create_data.key,
                proposed_type=create_data.memory_type.value,
                proposed_content=create_data.content,
                reason=f"AI agent {source_agent} proposed updating critical memory '{create_data.key}'",
                source_agent=source_agent,
            )
            prop_schema = MemoryChangeProposalSchema(
                id=proposal.id,
                tenant_id=proposal.tenant_id,
                memory_scope=MemoryScope(proposal.memory_scope),
                proposed_key=proposal.proposed_key,
                proposed_type=MemoryType(proposal.proposed_type),
                proposed_content=proposal.proposed_content,
                reason=proposal.reason,
                source_agent=proposal.source_agent,
                status=proposal.status,
                approval_id=proposal.approval_id,
                created_at=proposal.created_at,
            )
            return None, prop_schema

        if scope == MemoryScope.BUSINESS:
            item = await self.business_mem.add_memory(tenant_id, create_data)
        else:
            if not tenant_id:
                raise AppError("Tenant ID required for client memory", status_code=400)
            item = await self.client_mem.add_memory(tenant_id, create_data)

        return item, None

    async def list_proposals(
        self, tenant_id: uuid.UUID | None = None, status: str = "PENDING"
    ) -> list[MemoryChangeProposalSchema]:
        props = await self.repo.list_proposals(tenant_id=tenant_id, status=status)
        return [
            MemoryChangeProposalSchema(
                id=p.id,
                tenant_id=p.tenant_id,
                memory_scope=MemoryScope(p.memory_scope),
                proposed_key=p.proposed_key,
                proposed_type=MemoryType(p.proposed_type),
                proposed_content=p.proposed_content,
                reason=p.reason,
                source_agent=p.source_agent,
                status=p.status,
                approval_id=p.approval_id,
                created_at=p.created_at,
            )
            for p in props
        ]
