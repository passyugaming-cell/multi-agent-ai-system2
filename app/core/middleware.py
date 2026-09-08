from uuid import UUID
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.core.context import (
    reset_tenant_context,
    set_tenant_context,
    set_actor_context,
    reset_actor_context,
    AuthenticatedActor,
)
from app.core.auth import ROLE_PERMISSIONS
from app.core.auth_service import decode_access_token
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
    """Middleware to resolve tenant context from X-Tenant-ID header and populate authenticated actor context when valid Bearer token is provided."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        path = request.url.path

        # Skip tenant check for system, docs, auth endpoints, and external webhooks
        if (
            path in EXCLUDED_PATHS
            or path.startswith("/docs")
            or path.startswith("/openapi.json")
            or path.startswith("/api/v1/auth")
            or path.startswith("/api/v1/billing/webhooks")
            or path.startswith("/api/v1/webhooks")
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
        tenant_token = set_tenant_context(tenant_id)

        # Check for Authorization header and set server-side AuthenticatedActor context if valid
        actor_token = None
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            raw_jwt = auth_header.split(" ", 1)[1]
            jwt_payload = decode_access_token(raw_jwt)
            if jwt_payload and "tenant_ids" in jwt_payload and str(tenant_id) in jwt_payload["tenant_ids"]:
                user_uuid = UUID(jwt_payload["user_id"]) if jwt_payload.get("user_id") else None
                actor = AuthenticatedActor(
                    user_id=user_uuid,
                    tenant_id=tenant_id,
                    role="owner",
                    permissions=set(ROLE_PERMISSIONS["owner"]),
                )
                actor_token = set_actor_context(actor)

        try:
            response = await call_next(request)
            return response
        finally:
            reset_tenant_context(tenant_token)
            if actor_token is not None:
                reset_actor_context(actor_token)
