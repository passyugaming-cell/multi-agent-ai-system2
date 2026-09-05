import asyncio
import logging
from typing import Callable, TypeVar, Awaitable
from app.integrations.exceptions import TransientIntegrationError, PermanentIntegrationError

logger = logging.getLogger(__name__)

T = TypeVar("T")


async def execute_with_retry(
    func: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    initial_delay: float = 0.5,
    backoff_factor: float = 2.0,
) -> T:
    """Executes an async function with bounded retries and exponential backoff.
    Only retries transient errors; permanent errors fail immediately."""
    attempt = 0
    delay = initial_delay

    while True:
        try:
            attempt += 1
            return await func()
        except PermanentIntegrationError as pe:
            logger.warning("Permanent integration error encountered on attempt %d: %s", attempt, pe)
            raise pe
        except Exception as exc:
            is_transient = isinstance(exc, TransientIntegrationError) or any(
                term in str(exc).lower() for term in ["timeout", "rate limit", "503", "502", "connection reset"]
            )

            if not is_transient or attempt >= max_retries:
                logger.error("Execution failed after %d attempts (transient=%s): %s", attempt, is_transient, exc)
                if isinstance(exc, TransientIntegrationError) or isinstance(exc, PermanentIntegrationError):
                    raise exc
                raise TransientIntegrationError(f"Operation failed after {attempt} attempts: {exc}") from exc

            logger.info(
                "Transient error on attempt %d/%d. Retrying in %.2fs: %s",
                attempt,
                max_retries,
                delay,
                exc,
            )
            await asyncio.sleep(delay)
            delay *= backoff_factor
