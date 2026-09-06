from contextvars import ContextVar, Token
from typing import Optional, Any
from uuid import UUID
from dataclasses import dataclass, field


@dataclass
class AuthenticatedActor:
    user_id: Optional[UUID]
    tenant_id: UUID
    role: str
    permissions: set[str] = field(default_factory=set)


_tenant_context: ContextVar[Optional[UUID]] = ContextVar("tenant_context", default=None)
_actor_context: ContextVar[Optional[AuthenticatedActor]] = ContextVar("actor_context", default=None)


def get_tenant_context() -> Optional[UUID]:
    """Retrieve the current tenant ID from request context."""
    return _tenant_context.get()


# Alias for backward compatibility across modules
get_tenant_id = get_tenant_context


def set_tenant_context(tenant_id: UUID) -> Token[Optional[UUID]]:
    """Set the current tenant ID in request context and return the reset token."""
    return _tenant_context.set(tenant_id)


def reset_tenant_context(token: Token[Optional[UUID]]) -> None:
    """Reset the tenant context back to its previous state using the reset token."""
    _tenant_context.reset(token)


def get_actor_context() -> Optional[AuthenticatedActor]:
    """Retrieve the current authenticated actor from request context."""
    return _actor_context.get()


def set_actor_context(actor: AuthenticatedActor) -> Token[Optional[AuthenticatedActor]]:
    """Set the current authenticated actor in request context and return reset token."""
    return _actor_context.set(actor)


def reset_actor_context(token: Token[Optional[AuthenticatedActor]]) -> None:
    """Reset the actor context."""
    _actor_context.reset(token)
