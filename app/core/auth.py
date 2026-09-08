import uuid
import logging
from typing import Optional, Set
from fastapi import Header
from app.core.context import get_tenant_context, get_actor_context, AuthenticatedActor
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

ROLE_PERMISSIONS = {
    "owner": {
        "business.read", "business.write",
        "product.read", "product.write",
        "knowledge.read", "knowledge.write", "knowledge.approve",
        "VIEW_INTEGRATIONS", "MANAGE_INTEGRATIONS", "MANAGE_CREDENTIALS", "EXECUTE_INTEGRATION",
        "TEST_INTEGRATION", "VIEW_INTEGRATION_LOGS",
        "MANAGE_PAYMENTS", "VIEW_PAYMENT_STATUS", "REQUEST_REFUND", "APPROVE_REFUND",
        "VIEW_WHATSAPP_CONNECTION", "MANAGE_WHATSAPP_CONNECTION", "SEND_WHATSAPP_MESSAGE", "MANAGE_WHATSAPP_WEBHOOK",
    },
    "admin": {
        "business.read", "business.write",
        "product.read", "product.write",
        "knowledge.read", "knowledge.write", "knowledge.approve",
        "VIEW_INTEGRATIONS", "MANAGE_INTEGRATIONS", "MANAGE_CREDENTIALS", "EXECUTE_INTEGRATION",
        "TEST_INTEGRATION", "VIEW_INTEGRATION_LOGS",
        "MANAGE_PAYMENTS", "VIEW_PAYMENT_STATUS", "REQUEST_REFUND",
        "VIEW_WHATSAPP_CONNECTION", "MANAGE_WHATSAPP_CONNECTION", "SEND_WHATSAPP_MESSAGE",
    },
    "member": {
        "business.read",
        "product.read",
        "knowledge.read",
        "VIEW_INTEGRATIONS",
        "VIEW_PAYMENT_STATUS",
        "VIEW_WHATSAPP_CONNECTION",
    },
}


def resolve_actor_permissions(
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_authenticated_actor_id: Optional[str] = Header(None, alias="X-Authenticated-Actor-ID"),
    x_authenticated_tenant_id: Optional[str] = Header(None, alias="X-Authenticated-Tenant-ID"),
    x_actor_permissions: Optional[str] = Header(None, alias="X-Actor-Permissions"),
) -> Set[str]:
    """Resolves server-side permissions from trusted authenticated actor context and enforces strict tenant binding.

    Fail-closed security constraints:
    1. HTTP headers supplied by the client (X-Actor-Permissions, X-Actor-Role, X-Authenticated-Actor-ID, etc.)
       are NOT trusted as identity or permission authority.
    2. Any attempt to pass client-controlled permission or role headers without server-side authenticated
       actor context is REJECTED (HTTP 403 PERMISSION_DENIED).
    3. Authenticated actor tenant MUST match requested tenant context. Mismatches are REJECTED (HTTP 403 FORBIDDEN_CROSS_TENANT_ACCESS).
    4. Authenticated actor identity, role, and tenant membership MUST derive from server-side trusted ContextVar / authentication handler.
    5. NO fallback exists to infer identity or grant owner permissions from database records or X-Tenant-ID alone.
    """
    request_tenant_id = get_tenant_context()
    if not request_tenant_id:
        raise AppException(
            code="MISSING_TENANT_HEADER",
            message="Tenant context missing or invalid",
            status_code=400,
        )

    # 1. Reject attempts to forge client-controlled identity/role/permission headers
    if any(h is not None for h in (x_actor_role, x_authenticated_actor_id, x_authenticated_tenant_id, x_actor_permissions)):
        active_actor = get_actor_context()
        if not active_actor:
            raise AppException(
                code="PERMISSION_DENIED",
                message="Client-supplied identity or permission headers are not trusted. Server-side authentication required.",
                status_code=403,
            )

    # 2. Check trusted server-side ContextVar actor context
    active_actor = get_actor_context()
    if active_actor:
        if str(active_actor.tenant_id) != str(request_tenant_id):
            raise AppException(
                code="FORBIDDEN_CROSS_TENANT_ACCESS",
                message="Authenticated tenant does not match request tenant",
                status_code=403,
            )
        return set(active_actor.permissions)

    # 3. Fail closed: No fallback to database user or X-Tenant-ID inference
    raise AppException(
        code="PERMISSION_DENIED",
        message="Authentication required: no trusted server-side actor context found",
        status_code=403,
    )
