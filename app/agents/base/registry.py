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

        # Security Boundary Enforcement: FAIL-CLOSED verification for Owner AI execution
        if request.target_agent == "owner_ai":
            actor = get_actor_context()
            if (
                actor is None
                or not getattr(actor, "is_platform_owner", False)
                or request.source in ("workflow", "agent_delegation")
                or (request.source_agent and request.source_agent != "owner_ai")
            ):
                logger.warning(
                    "Blocked attempt to delegate or execute Owner AI: actor=%s, is_platform_owner=%s, source='%s', source_agent='%s'",
                    actor.user_id if actor else None,
                    getattr(actor, "is_platform_owner", False) if actor else False,
                    request.source,
                    request.source_agent,
                )
                return AgentResult(
                    request_id=request.request_id,
                    agent=request.target_agent,
                    status=AgentRequestStatus.BLOCKED,
                    error="Execution of Owner AI requires an authenticated Human Platform Owner context. Requests from missing actors, tenant AIs, workflows, or non-platform-owner actors are strictly forbidden.",
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
