from decimal import Decimal
import logging
import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_gateway.schemas import AIResponse, AIRequest
from app.repositories.domain import AIUsageRepository
from app.billing.usage import UsageService, UsageMetric, calculate_ai_credits

logger = logging.getLogger("ai_gateway.usage")

PRICE_PER_INPUT_TOKEN = Decimal("0.000000075")
PRICE_PER_OUTPUT_TOKEN = Decimal("0.000000300")


def calculate_estimated_cost(
    input_tokens: int | None, output_tokens: int | None
) -> Decimal | None:
    if input_tokens is None or output_tokens is None:
        return None
    cost = (Decimal(input_tokens) * PRICE_PER_INPUT_TOKEN) + (
        Decimal(output_tokens) * PRICE_PER_OUTPUT_TOKEN
    )
    return cost.quantize(Decimal("0.000001"))


class UsageTracker:
    """Tracks and records AI usage and token costs, integrating with billing usage engine."""

    async def record_usage(
        self,
        db_session: AsyncSession,
        request: AIRequest,
        response: AIResponse | None,
        request_id: str,
        latency_ms: float,
        error: Exception | None = None,
    ) -> None:
        repo = AIUsageRepository(db_session)

        input_tokens = response.input_tokens if response else None
        output_tokens = response.output_tokens if response else None
        total_tokens = response.total_tokens if response else None
        model = response.model if response else "gemini-3.1-flash-lite"
        usage_status = response.usage_status if response else "UNKNOWN"

        cost = calculate_estimated_cost(input_tokens, output_tokens)

        try:
            await repo.create(
                tenant_id=request.tenant_id,
                request_id=request_id,
                task_type=request.task_type,
                model=model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                estimated_cost=cost,
                latency_ms=latency_ms,
                success=error is None,
                usage_status=usage_status,
                error_message=str(error) if error else None,
            )
        except Exception as e:
            logger.error(f"Failed to persist AI usage record for request {request_id}: {e}")

        # Integrate with billing usage engine
        if request.tenant_id and error is None:
            try:
                credits_consumed = calculate_ai_credits(total_tokens)
                tenant_uuid = uuid.UUID(request.tenant_id) if isinstance(request.tenant_id, str) else request.tenant_id
                usage_service = UsageService(db_session)
                await usage_service.check_and_increment_usage(
                    tenant_id=tenant_uuid,
                    metric=UsageMetric.AI_CREDITS,
                    quantity=credits_consumed,
                    source="AIGateway",
                    metadata={
                        "request_id": request_id,
                        "task_type": request.task_type,
                        "model": model,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "total_tokens": total_tokens,
                        "estimated_provider_cost": str(cost) if cost is not None else None,
                    },
                    policy="WARN",  # Warn or allow execution record
                )
            except Exception as e:
                logger.warning(f"Failed to record billing AI credits for tenant {request.tenant_id}: {e}")
