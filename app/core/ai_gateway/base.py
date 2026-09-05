from abc import ABC, abstractmethod
from app.core.ai_gateway.schemas import AIRequest, AIResponse


class AIProvider(ABC):
    """Abstract interface for AI providers."""

    @abstractmethod
    async def generate(self, request: AIRequest, request_id: str) -> AIResponse:
        """Generates response using underlying AI provider."""
        pass
