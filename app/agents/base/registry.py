import logging
from typing import Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import BaseAgent
from app.agents.base.schemas import AgentRequest, AgentResult, AgentRequestStatus
from app.agents.base.exceptions import AgentExecutionError, AgentRecursionError, AgentPermissionError
from app.agents.base.permissions import AGENT_PERMISSIONS
from app.core.context import get_actor_context

logger = logging.getLogger(__name__)

MAX_DELEGATION_DEPTH = 3


class AgentRegistry:
    """Central registry managing specialist AI agents, capability discovery, and delegation."""

    def __init__(self) -> None:
        self._agents: Dict[str, BaseAgent] = {}

    def register_agent(self, agent: BaseAgent) -> None:
        """Register a specialist agent instance."""
        self._agents[agent.name] = agent
        logger.info("Registered specialist agent: %s", agent.name)

    def get_agent(self, agent_name: str) -> BaseAgent:
        """Retrieve a registered agent by name."""
        agent = self._agents.get(agent_name)
        if not agent:
            raise AgentExecutionError(f"Specialist agent '{agent_name}' is not registered.")
        return agent

    def is_agent_enabled(self, agent_name: str) -> bool:
        """Check if an agent is registered and enabled."""
        agent = self._agents.get(agent_name)
        return agent is not None and agent.enabled

    def list_agents(self) -> list[dict[str, Any]]:
        """List registered agents and their capability metadata."""
        capabilities = []
        for name, agent in self._agents.items():
            perms = AGENT_PERMISSIONS.get(name, {})
            capabilities.append({
                "name": name,
                "enabled": agent.enabled,
                "allowed_tools": perms.get("allowed_tools", []),
                "forbidden_actions": perms.get("forbidden_actions", []),
                "read_only": perms.get("read_only", False),
            })
        return capabilities

    async def delegate_task(
        self,
        request: AgentRequest,
        db_session: AsyncSession,
    ) -> AgentResult:
        """Controlled agent-to-agent delegation with recursion depth protection."""
        if request.delegation_depth >= MAX_DELEGATION_DEPTH:
            logger.error(
                "Delegation depth limit exceeded (%d >= %d) from %s to %s",
                request.delegation_depth,
                MAX_DELEGATION_DEPTH,
                request.source_agent,
                request.target_agent,
            )
            return AgentResult(
                request_id=request.request_id,
                agent=request.target_agent,
                status=AgentRequestStatus.BLOCKED,
                error=f"Delegation depth limit exceeded (max depth {MAX_DELEGATION_DEPTH}).",
                correlation_id=request.correlation_id,
            )

        # Security Boundary Enforcement: Non-owner callers, specialist agents, and workflows CANNOT call Owner AI
        if request.target_agent == "owner_ai":
            actor = get_actor_context()
            if (
                request.source in ("workflow", "agent_delegation")
                or (request.source_agent and request.source_agent != "owner_ai")
                or (actor is not None and actor.role != "owner")
            ):
                logger.warning(
                    "Blocked attempt to delegate or execute Owner AI from source='%s', source_agent='%s', actor_role='%s'",
                    request.source,
                    request.source_agent,
                    actor.role if actor else None,
                )
                return AgentResult(
                    request_id=request.request_id,
                    agent=request.target_agent,
                    status=AgentRequestStatus.BLOCKED,
                    error="Delegation or execution of Owner AI from tenant AI, workflows, or non-owner callers is strictly forbidden.",
                    correlation_id=request.correlation_id,
                )

        agent = self.get_agent(request.target_agent)

        # Enforce target agent enabled check
        if not agent.enabled:
            return AgentResult(
                request_id=request.request_id,
                agent=request.target_agent,
                status=AgentRequestStatus.BLOCKED,
                error=f"Target agent '{request.target_agent}' is disabled.",
                correlation_id=request.correlation_id,
            )

        # Increment delegation depth for sub-request, preserving workflow source
        new_source = request.source if request.source in ("workflow", "api") else "agent_delegation"
        sub_request = request.model_copy(
            update={
                "delegation_depth": request.delegation_depth + 1,
                "source": new_source,
            }
        )

        return await agent.run(sub_request, db_session)


# Global singleton instance
agent_registry = AgentRegistry()
