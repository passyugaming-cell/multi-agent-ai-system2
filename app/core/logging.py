import json
import logging
import sys
import time
from typing import Any
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings
from app.core.context import get_tenant_context


class JSONFormatter(logging.Formatter):
    """Structured JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Include tenant ID if available
        tenant_id = get_tenant_context()
        if tenant_id:
            log_data["tenant_id"] = str(tenant_id)

        # Include extra fields if passed
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            for k, v in record.extra_fields.items():
                if k not in log_data:
                    log_data[k] = v

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data)


def setup_logging() -> logging.Logger:
    """Configure structured logging for the application."""
    logger = logging.getLogger("ai_business_os")
    logger.setLevel(settings.LOG_LEVEL.upper())

    # Avoid duplicate handlers if already configured
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setLevel(settings.LOG_LEVEL.upper())
        handler.setFormatter(JSONFormatter())
        logger.addHandler(handler)

    logger.propagate = False
    return logger


logger = setup_logging()


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log details about every incoming HTTP request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start_time = time.perf_counter()

        response = await call_next(request)

        process_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        tenant_id = getattr(request.state, "tenant_id", None) or get_tenant_context()

        log_data = {
            "extra_fields": {
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": process_time_ms,
                "tenant_id": str(tenant_id) if tenant_id else None,
            }
        }

        logger.info(
            f"{request.method} {request.url.path} {response.status_code} - {process_time_ms}ms",
            extra=log_data,
        )

        return response
