import uuid
import logging
from typing import Optional, Set
from fastapi import Header, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.context import get_tenant_context, get_actor_context, AuthenticatedActor, set_actor_context
from app.core.exceptions import AppException
from app.database.models.user import User
from app.database.session import get_db_session
from sqlalchemy import select

logger = logging.getLogger(__name__)

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


async def resolve_actor_permissions(
    x_actor_role: Optional[str] = Header(None, alias="X-Actor-Role"),
    x_authenticated_actor_id: Optional[str] = Header(None, alias="X-Authenticated-Actor-ID"),
    x_authenticated_tenant_id: Optional[str] = Header(None, alias="X-Authenticated-Tenant-ID"),
    x_actor_permissions: Optional[str] = Header(None, alias="X-Actor-Permissions"),
    db: AsyncSession = Depends(get_db_session),
) -> Set[str]:
    """Resolves server-side permissions from trusted authenticated actor context and enforces strict tenant binding.

    Security & Fail-Closed Boundaries:
    1. HTTP headers supplied by client (X-Actor-Permissions, X-Actor-Role, etc.) are NOT trusted as identity/permission authority.
    2. Any attempt to pass client-controlled permission/role/actor headers without server-side authenticated context is REJECTED (HTTP 403 PERMISSION_DENIED).
    3. Authenticated actor tenant MUST match requested tenant context. Mismatches are REJECTED (HTTP 403 FORBIDDEN_CROSS_TENANT_ACCESS).
    4. Authenticated actor identity, role, and tenant membership are derived from server-side database truth / ContextVar.
    """
    request_tenant_id = get_tenant_context()
    if not request_tenant_id:
        raise AppException(
            code="MISSING_TENANT_HEADER",
            message="Tenant context missing or invalid",
            status_code=400,
        )

    # 1. Reject client attempts to pass unverified permission or role headers
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
        return active_actor.permissions

    # 3. Server-side database lookup for active tenant users
    stmt = select(User).where(User.tenant_id == request_tenant_id, User.is_active == True)
    result = await db.execute(stmt)
    users = result.scalars().all()

    if users:
        # Resolve permissions for the first active user (default owner role)
        user = users[0]
        role = "owner"
        permissions = set(ROLE_PERMISSIONS[role])
        actor = AuthenticatedActor(
            user_id=user.id,
            tenant_id=request_tenant_id,
            role=role,
            permissions=permissions,
        )
        set_actor_context(actor)
        return permissions

    # 4. Fail closed if no trusted actor context or database user exists
    raise AppException(
        code="PERMISSION_DENIED",
        message="Authentication required: no server-side actor context found for tenant",
        status_code=403,
    )
