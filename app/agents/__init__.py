from app.agents.base import (
    BaseAgent,
    AgentRegistry,
    agent_registry,
    AgentRequest,
    AgentResult,
    AgentRequestStatus,
    ToolRequest,
    ToolResult,
)
from app.agents.factory import register_all_agents

# Automatically register default agents
register_all_agents(agent_registry)

__all__ = [
    "BaseAgent",
    "AgentRegistry",
    "agent_registry",
    "AgentRequest",
    "AgentResult",
    "AgentRequestStatus",
    "ToolRequest",
    "ToolResult",
    "register_all_agents",
]
