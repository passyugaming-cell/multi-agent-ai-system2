from uuid import UUID
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.context import reset_tenant_context, set_tenant_context
from app.database.session import async_session_factory
from app.tenants.repository import TenantRepository


EXCLUDED_PATHS = {
    "/",
    "/health",
    "/health/db",
    "/api/v1/health",
    "/api/v1/health/db",
    "/docs",
    "/openapi.json",
    "/redoc",
}


class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware to resolve tenant context from X-Tenant-ID header."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Skip tenant check for system, docs, and external provider webhooks
        if (
            path in EXCLUDED_PATHS
            or path.startswith("/docs")
            or path.startswith("/openapi.json")
            or path.startswith("/api/v1/billing/webhooks")
        ):
            return await call_next(request)

        tenant_header = request.headers.get("X-Tenant-ID")

        if not tenant_header:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "MISSING_TENANT_HEADER",
                        "message": "X-Tenant-ID header is required",
                    }
                },
            )

        try:
            tenant_id = UUID(tenant_header)
        except ValueError:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "INVALID_TENANT_ID",
                        "message": "X-Tenant-ID header must be a valid UUID",
                    }
                },
            )

        async with async_session_factory() as db:
            repo = TenantRepository(db)
            tenant = await repo.get_by_id(tenant_id)

            if not tenant:
                return JSONResponse(
                    status_code=404,
                    content={
                        "error": {
                            "code": "TENANT_NOT_FOUND",
                            "message": "Tenant not found",
                        }
                    },
                )

            if not tenant.is_active:
                return JSONResponse(
                    status_code=403,
                    content={
                        "error": {
                            "code": "TENANT_INACTIVE",
                            "message": "Tenant is inactive",
                        }
                    },
                )

        request.state.tenant_id = str(tenant_id)
        token = set_tenant_context(tenant_id)
        try:
            response = await call_next(request)
            return response
        finally:
            reset_tenant_context(token)
