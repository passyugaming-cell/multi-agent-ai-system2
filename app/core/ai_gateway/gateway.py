import logging
import time
import uuid
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_gateway.base import AIProvider
from app.core.ai_gateway.gemini import GeminiProvider
from app.core.ai_gateway.rate_limiter import RateLimiter
from app.core.ai_gateway.schemas import AIRequest, AIResponse
from app.core.ai_gateway.usage import UsageTracker
from app.core.ai_gateway.exceptions import AIGatewayError

logger = logging.getLogger("ai_gateway")


class AIGateway:
    """Universal AI Gateway managing AI providers, rate limiting, and usage tracking."""

    def __init__(
        self,
        provider: AIProvider | None = None,
        rate_limiter: RateLimiter | None = None,
        usage_tracker: UsageTracker | None = None,
    ):
        self.provider = provider or GeminiProvider()
        self.rate_limiter = rate_limiter or RateLimiter()
        self.usage_tracker = usage_tracker or UsageTracker()

    @staticmethod
    def generate_request_id() -> str:
        return f"ai_req_{uuid.uuid4().hex}"

    async def generate(
        self,
        request: AIRequest,
        db_session: AsyncSession | None = None,
    ) -> AIResponse:
        request_id = self.generate_request_id()
        start_time = time.time()

        await self.rate_limiter.check_rate_limit(request.tenant_id)

        response: AIResponse | None = None
        error: Exception | None = None

        try:
            response = await self.provider.generate(request, request_id=request_id)
            return response
        except Exception as exc:
            error = exc
            logger.error(
                f"AI Request {request_id} failed for tenant {request.tenant_id}: {exc}"
            )
            raise exc
        finally:
            latency_ms = (time.time() - start_time) * 1000.0
            if db_session is not None:
                await self.usage_tracker.record_usage(
                    db_session=db_session,
                    request=request,
                    response=response,
                    request_id=request_id,
                    latency_ms=latency_ms,
                    error=error,
                )
