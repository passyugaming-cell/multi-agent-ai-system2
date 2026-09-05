from contextvars import ContextVar, Token
from typing import Optional
from uuid import UUID

_tenant_context: ContextVar[Optional[UUID]] = ContextVar("tenant_context", default=None)


def get_tenant_context() -> Optional[UUID]:
    """Retrieve the current tenant ID from request context."""
    return _tenant_context.get()


def set_tenant_context(tenant_id: UUID) -> Token[Optional[UUID]]:
    """Set the current tenant ID in request context and return the reset token."""
    return _tenant_context.set(tenant_id)


def reset_tenant_context(token: Token[Optional[UUID]]) -> None:
    """Reset the tenant context back to its previous state using the reset token."""
    _tenant_context.reset(token)
