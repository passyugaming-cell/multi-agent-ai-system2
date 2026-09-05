import time
from typing import Dict, List
from uuid import UUID
from app.core.ai_gateway.exceptions import AIRateLimitError


class RateLimiter:
    """In-memory rate limiter per tenant designed to be swappable with Redis."""

    def __init__(self, requests_per_minute: int = 60):
        self.requests_per_minute = requests_per_minute
        self.tenant_requests: Dict[UUID, List[float]] = {}

    async def check_rate_limit(self, tenant_id: UUID) -> None:
        now = time.time()
        window_start = now - 60.0

        if tenant_id not in self.tenant_requests:
            self.tenant_requests[tenant_id] = []

        timestamps = self.tenant_requests[tenant_id]
        self.tenant_requests[tenant_id] = [t for t in timestamps if t > window_start]

        if len(self.tenant_requests[tenant_id]) >= self.requests_per_minute:
            raise AIRateLimitError(
                f"Rate limit exceeded for tenant {tenant_id}. Max {self.requests_per_minute} requests per minute."
            )

        self.tenant_requests[tenant_id].append(now)
