import logging
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import BaseAgent
from app.agents.base.schemas import AgentRequest, AgentResult, AgentRequestStatus
from app.agents.owner_ai.prompts import OWNER_AI_SYSTEM_INSTRUCTION
from app.agents.owner_ai.orchestrator import OwnerAIOrchestrator
from app.core.ai_gateway import AIGateway

logger = logging.getLogger(__name__)


class OwnerAIAgent(BaseAgent):
    """Owner AI Central Orchestration Agent for Human Owner."""

    def __init__(
        self,
        ai_gateway: AIGateway | None = None,
        enabled: bool = True,
    ):
        super().__init__(
            name="owner_ai",
            system_instruction=OWNER_AI_SYSTEM_INSTRUCTION,
            ai_gateway=ai_gateway,
            enabled=enabled,
        )

    async def process_task(
        self,
        request: AgentRequest,
        db_session: AsyncSession,
    ) -> AgentResult:
        """Processes task by invoking OwnerAIOrchestrator."""
        orchestrator = OwnerAIOrchestrator(db_session)
        return await orchestrator.orchestrate(
            tenant_id=request.tenant_id,
            objective=request.objective,
            context=request.context,
            correlation_id=request.correlation_id,
            delegation_depth=request.delegation_depth,
        )
