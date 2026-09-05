from app.agents.base.registry import agent_registry, AgentRegistry
from app.agents.sales.agent import SalesAgent
from app.agents.client_manager.agent import ClientManagerAgent
from app.agents.support.agent import SupportAgent
from app.agents.data_manager.agent import DataManagerAgent
from app.agents.analyst.agent import AnalystAgent
from app.agents.owner_ai.agent import OwnerAIAgent


def register_all_agents(registry: AgentRegistry = agent_registry) -> AgentRegistry:
    """Register all specialist agents and Owner AI into the registry if not already registered."""
    agents = [
        SalesAgent(),
        ClientManagerAgent(),
        SupportAgent(),
        DataManagerAgent(),
        AnalystAgent(),
        OwnerAIAgent(),
    ]
    for agent in agents:
        try:
            registry.get_agent(agent.name)
        except Exception:
            registry.register_agent(agent)
    return registry
