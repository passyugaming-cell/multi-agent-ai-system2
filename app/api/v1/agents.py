from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
import uuid

from app.database.session import get_db
from app.core.context import get_tenant_context, get_actor_context
from app.core.auth import resolve_actor_permissions
from app.core.exceptions import AppException
from app.agents import agent_registry, AgentRequest, AgentResult, AgentRequestStatus

router = APIRouter(prefix="/agents", tags=["Specialist AI Agents"])


@router.get(
    "",
    summary="List registered specialist AI agents and capabilities",
)
async def list_agents():
    """Returns metadata, allowed tools, and enabled status for registered agents."""
    return {"agents": agent_registry.list_agents()}


@router.get(
    "/{agent_name}",
    summary="Get details and capabilities for a specific specialist agent",
)
async def get_agent_details(agent_name: str):
    """Returns details for a specific registered agent."""
    try:
        agent = agent_registry.get_agent(agent_name)
        capabilities = [a for a in agent_registry.list_agents() if a["name"] == agent_name]
        return capabilities[0] if capabilities else {"name": agent_name, "enabled": agent.enabled}
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent '{agent_name}' not found.",
        )


@router.post(
    "/{agent_name}/run",
    response_model=AgentResult,
    summary="Execute a specialist AI agent task",
)
async def run_agent(
    agent_name: str,
    request_body: AgentRequest,
    db: AsyncSession = Depends(get_db),
    actor_perms: set[str] = Depends(resolve_actor_permissions),
):
    """Execute a controlled agent request safely under current tenant context."""
    tenant_id = get_tenant_context()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid tenant context.",
        )

    # Enforce tenant isolation: tenant_id MUST match header/context
    request_tenant_id = request_body.tenant_id

    if request_tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agent request tenant_id does not match active request tenant context.",
        )

    if request_body.target_agent != agent_name:
        request_body = request_body.model_copy(update={"target_agent": agent_name})

    if not agent_registry.is_agent_enabled(agent_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Agent '{agent_name}' is disabled or not registered.",
        )

    actor = get_actor_context()
    if agent_name == "owner_ai" and (not actor or not getattr(actor, "is_platform_owner", False)):
        raise AppException(
            code="PERMISSION_DENIED",
            message="Execution of Owner AI is restricted strictly to Human Platform Owners.",
            status_code=403,
        )

    result = await agent_registry.delegate_task(request_body, db)
    return result
