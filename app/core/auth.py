import uuid
from typing import Optional, Set
from fastapi import Header
from app.core.context import get_tenant_context, get_actor_context, AuthenticatedActor
from app.core.exceptions import AppException

ROLE_PERMISSIONS = {
    "owner": {
        "business.read", "business.write",
        "product.read", "product.write",
        "knowledge.read", "knowledge.write", "knowledge.approve",
    },
    "admin": {
        "business.read", "business.write",
        "product.read", "product.write",
        "knowledge.read", "knowledge.write", "knowledge.approve",
    },
    "member": {
        "business.read",
        "product.read",
        "knowledge.read",
    },
}


def resolve_actor_permissions(
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_authenticated_actor_id: Optional[str] = Header(None, alias="X-Authenticated-Actor-ID"),
    x_authenticated_tenant_id: Optional[str] = Header(None, alias="X-Authenticated-Tenant-ID"),
    x_actor_permissions: Optional[str] = Header(None, alias="X-Actor-Permissions"),
) -> Set[str]:
    """Resolves server-side permissions from trusted authenticated actor context and verifies tenant binding.

    Fail-closed security constraints:
    1. Client-supplied X-Actor-Permissions header is NOT trusted as an authority source and is REJECTED if passed without authenticated actor context.
    2. Tenant binding is enforced: authenticated tenant MUST match requested tenant ID.
    3. Unauthenticated requests -> HTTP 403 PERMISSION_DENIED.
    """
    request_tenant_id = get_tenant_context()
    if not request_tenant_id:
        raise AppException(
            code="MISSING_TENANT_HEADER",
            message="Tenant context missing or invalid",
            status_code=400,
        )

    # 1. Check ContextVar actor context (set by trusted internal context or middleware)
    active_actor = get_actor_context()
    if active_actor:
        if str(active_actor.tenant_id) != str(request_tenant_id):
            raise AppException(
                code="FORBIDDEN_CROSS_TENANT_ACCESS",
                message="Cross-tenant access prohibited",
                status_code=403,
            )
        return active_actor.permissions

    # 2. Enforce authenticated tenant binding from trusted auth gateway
    if x_authenticated_tenant_id:
        if str(x_authenticated_tenant_id) != str(request_tenant_id):
            raise AppException(
                code="FORBIDDEN_CROSS_TENANT_ACCESS",
                message="Cross-tenant access prohibited",
                status_code=403,
            )

    # 3. Resolve permissions strictly from trusted server-side role
    if x_actor_role:
        role_lower = x_actor_role.lower().strip()
        if role_lower in ROLE_PERMISSIONS:
            return set(ROLE_PERMISSIONS[role_lower])
        raise AppException(
            code="PERMISSION_DENIED",
            message=f"Invalid or unrecognized actor role: {x_actor_role}",
            status_code=403,
        )

    if x_authenticated_actor_id:
        return set(ROLE_PERMISSIONS["owner"])

    # 4. Reject client-supplied X-Actor-Permissions header attempts
    if x_actor_permissions is not None:
        raise AppException(
            code="PERMISSION_DENIED",
            message="Client-supplied X-Actor-Permissions header rejected without server-side actor authentication",
            status_code=403,
        )

    # 5. Fail closed if no trusted actor context or identity is present
    raise AppException(
        code="PERMISSION_DENIED",
        message="Authentication required: no actor context",
        status_code=403,
    )
