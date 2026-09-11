import logging
from uuid import UUID
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from sqlalchemy import select

from app.core.context import (
    reset_tenant_context,
    set_tenant_context,
    set_actor_context,
    reset_actor_context,
    AuthenticatedActor,
)
from app.core.auth import ROLE_PERMISSIONS
from app.core.auth_service import verify_and_decode_token
from app.database.session import async_session_factory
from app.database.models.user import User
from app.tenants.repository import TenantRepository

logger = logging.getLogger(__name__)


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
    """Middleware to resolve tenant context from X-Tenant-ID header and populate authenticated actor context from database user role."""

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
        tenant_id = None

        if tenant_header:
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
        elif path.endswith("/google-calendar/callback") or path.endswith("/google-sheets/callback"):
            # Recover tenant_id from cryptographically signed OAuth state when X-Tenant-ID header is absent on redirect
            state_param = request.query_params.get("state")
            if not state_param:
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "INVALID_OAUTH_STATE",
                            "message": "Invalid OAuth state",
                        }
                    },
                )
            try:
                from app.integrations.oauth import parse_oauth_state_payload
                state_payload = parse_oauth_state_payload(state_param)
                tenant_id = UUID(state_payload["tenant_id"])
            except Exception as exc:
                logger.warning("OAuth callback state parsing failed: %s", exc)
                return JSONResponse(
                    status_code=400,
                    content={
                        "error": {
                            "code": "INVALID_OAUTH_STATE",
                            "message": "Invalid OAuth state",
                        }
                    },
                )

        if not tenant_id:
            return JSONResponse(
                status_code=400,
                content={
                    "error": {
                        "code": "MISSING_TENANT_HEADER",
                        "message": "X-Tenant-ID header is required",
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

            # Validate authentication and resolve per-tenant user role from database
            actor_token = None
            auth_header = request.headers.get("Authorization")
            if auth_header and auth_header.startswith("Bearer "):
                raw_jwt = auth_header.split(" ", 1)[1]
                jwt_payload = await verify_and_decode_token(raw_jwt)
                if jwt_payload and "sub" in jwt_payload and "tenant_ids" in jwt_payload:
                    if str(tenant_id) in jwt_payload["tenant_ids"]:
                        email = jwt_payload["sub"]
                        user_stmt = select(User).where(
                            User.email == email,
                            User.tenant_id == tenant_id,
                            User.is_active == True,
                        )
                        user_result = await db.execute(user_stmt)
                        user = user_result.scalars().first()

                        if user:
                            role = getattr(user, "role", "owner")
                            permissions = ROLE_PERMISSIONS.get(role, set())
                            actor = AuthenticatedActor(
                                user_id=user.id,
                                tenant_id=tenant_id,
                                role=role,
                                permissions=set(permissions),
                                is_platform_owner=getattr(user, "is_platform_owner", False),
                            )
                            actor_token = set_actor_context(actor)

        request.state.tenant_id = str(tenant_id)
        tenant_token = set_tenant_context(tenant_id)

        try:
            response = await call_next(request)
            return response
        finally:
            reset_tenant_context(tenant_token)
            if actor_token is not None:
                reset_actor_context(actor_token)
