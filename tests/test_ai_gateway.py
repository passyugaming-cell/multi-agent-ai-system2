import pytest
from decimal import Decimal
import uuid
from app.core.ai_gateway import (
    AIGateway,
    AIRequest,
    AIRateLimitError,
    AITimeoutError,
    AIAuthenticationError,
)
from app.core.ai_gateway.usage import calculate_estimated_cost
from tests.fake_ai import FakeAIProvider


@pytest.mark.asyncio
async def test_ai_gateway_provider_invocation():
    fake_provider = FakeAIProvider(default_text="Hello from AI")
    gateway = AIGateway(provider=fake_provider)

    tenant_id = uuid.uuid4()
    req = AIRequest(
        tenant_id=tenant_id,
        task_type="test_task",
        system_instruction="You are a bot",
        user_message="Hi",
    )

    resp = await gateway.generate(req)
    assert resp.text == "Hello from AI"
    assert resp.model == "fake-gemini-model"
    assert resp.input_tokens == 10
    assert resp.output_tokens == 20
    assert resp.total_tokens == 30
    assert resp.request_id.startswith("ai_req_")
    assert len(fake_provider.calls) == 1


@pytest.mark.asyncio
async def test_ai_gateway_error_handling():
    fake_provider = FakeAIProvider(
        should_fail=True,
        failure_exception=AITimeoutError("Request timed out"),
    )
    gateway = AIGateway(provider=fake_provider)

    tenant_id = uuid.uuid4()
    req = AIRequest(
        tenant_id=tenant_id,
        task_type="test_task",
        system_instruction="You are a bot",
        user_message="Hi",
    )

    with pytest.raises(AITimeoutError):
        await gateway.generate(req)


@pytest.mark.asyncio
async def test_ai_gateway_rate_limiting():
    fake_provider = FakeAIProvider(default_text="OK")
    gateway = AIGateway(provider=fake_provider)
    gateway.rate_limiter.requests_per_minute = 2

    tenant_id = uuid.uuid4()
    req = AIRequest(
        tenant_id=tenant_id,
        task_type="test_task",
        system_instruction="Bot",
        user_message="Hi",
    )

    await gateway.generate(req)
    await gateway.generate(req)

    with pytest.raises(AIRateLimitError):
        await gateway.generate(req)


def test_cost_calculation():
    cost = calculate_estimated_cost(1000, 2000)
    # (1000 * 0.000000075) + (2000 * 0.000000300) = 0.000075 + 0.0006 = 0.000675
    assert cost == Decimal("0.000675")
