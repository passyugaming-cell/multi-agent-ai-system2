from decimal import Decimal
from uuid import UUID
from app.core.ai_gateway.base import AIProvider
from app.core.ai_gateway.schemas import AIRequest, AIResponse


class FakeAIProvider(AIProvider):
    """Fake AI Provider for unit/integration tests without calling live Gemini API."""

    def __init__(
        self,
        default_text: str = "Fake AI response text",
        default_structured_output: any = None,
        should_fail: bool = False,
        failure_exception: Exception | None = None,
    ):
        self.default_text = default_text
        self.default_structured_output = default_structured_output
        self.should_fail = should_fail
        self.failure_exception = failure_exception
        self.calls: list[AIRequest] = []

    async def generate(self, request: AIRequest, request_id: str) -> AIResponse:
        self.calls.append(request)

        if self.should_fail:
            if self.failure_exception:
                raise self.failure_exception
            raise RuntimeError("Fake AI Provider raised configured failure.")

        return AIResponse(
            text=self.default_text,
            model="fake-gemini-model",
            input_tokens=10,
            output_tokens=20,
            total_tokens=30,
            estimated_cost=Decimal("0.000006"),
            finish_reason="STOP",
            request_id=request_id,
            structured_output=self.default_structured_output,
            usage_status="EXACT",
        )
