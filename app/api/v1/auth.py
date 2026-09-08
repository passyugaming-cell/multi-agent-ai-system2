import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.database.models.user import User
from app.database.models.tenant import Tenant
from app.core.auth_service import (
    verify_password,
    create_access_token,
    verify_and_decode_token,
    revoke_token_redis,
)
from app.core.exceptions import AppException

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    lifecycle_state: str


class UserAuthResponse(BaseModel):
    id: str
    email: str


class AuthTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserAuthResponse
    tenants: List[TenantResponse]
    active_tenant_id: Optional[str] = None


class SelectTenantRequest(BaseModel):
    tenant_id: str


class SelectTenantResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    active_tenant_id: str
    status: str = "ACTIVE"


@router.post("/login", response_model=AuthTokenResponse)
async def login(
    payload: LoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """Authenticate user with email and password across authorized tenants."""
    stmt = select(User).where(User.email == payload.email, User.is_active == True)
    result = await db.execute(stmt)
    users = result.scalars().all()

    if not users:
        raise AppException(
            code="INVALID_CREDENTIALS",
            message="Invalid email or password",
            status_code=401,
        )

    # Check password against any matching user record for this email
    authenticated_user = None
    for u in users:
        if verify_password(payload.password, u.password_hash):
            authenticated_user = u
            break

    if not authenticated_user:
        raise AppException(
            code="INVALID_CREDENTIALS",
            message="Invalid email or password",
            status_code=401,
        )

    # Collect authorized active tenants
    tenant_ids = [u.tenant_id for u in users]
    tenant_stmt = select(Tenant).where(Tenant.id.in_(tenant_ids), Tenant.is_active == True)
    tenant_result = await db.execute(tenant_stmt)
    tenants = tenant_result.scalars().all()

    if not tenants:
        raise AppException(
            code="NO_ACTIVE_TENANTS",
            message="User has no active authorized tenants",
            status_code=403,
        )

    tenant_responses = [
        TenantResponse(
            id=str(t.id),
            name=t.name,
            slug=t.slug,
            lifecycle_state=t.lifecycle_state,
        )
        for t in tenants
    ]

    active_tenant_id = str(tenants[0].id) if len(tenants) == 1 else None

    token_payload = {
        "sub": authenticated_user.email,
        "user_id": str(authenticated_user.id),
        "tenant_ids": [str(t.id) for t in tenants],
        "active_tenant_id": active_tenant_id,
        "jti": str(uuid.uuid4()),
    }
    token = create_access_token(token_payload)

    return AuthTokenResponse(
        access_token=token,
        user=UserAuthResponse(
            id=str(authenticated_user.id),
            email=authenticated_user.email,
        ),
        tenants=tenant_responses,
        active_tenant_id=active_tenant_id,
    )


@router.get("/me", response_model=AuthTokenResponse)
async def get_me(
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Return current user info and authorized tenant list from validated Bearer token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise AppException(
            code="UNAUTHORIZED",
            message="Authentication required",
            status_code=401,
        )

    token = authorization.split(" ", 1)[1]
    payload = await verify_and_decode_token(token)
    if not payload or "sub" not in payload:
        raise AppException(
            code="SESSION_EXPIRED",
            message="Your session has expired. Please sign in again.",
            status_code=401,
        )

    email = payload["sub"]
    stmt = select(User).where(User.email == email, User.is_active == True)
    result = await db.execute(stmt)
    users = result.scalars().all()

    if not users:
        raise AppException(
            code="UNAUTHORIZED",
            message="User not found or inactive",
            status_code=401,
        )

    tenant_ids = [u.tenant_id for u in users]
    tenant_stmt = select(Tenant).where(Tenant.id.in_(tenant_ids), Tenant.is_active == True)
    tenant_result = await db.execute(tenant_stmt)
    tenants = tenant_result.scalars().all()

    tenant_responses = [
        TenantResponse(
            id=str(t.id),
            name=t.name,
            slug=t.slug,
            lifecycle_state=t.lifecycle_state,
        )
        for t in tenants
    ]

    return AuthTokenResponse(
        access_token=token,
        user=UserAuthResponse(
            id=str(users[0].id),
            email=users[0].email,
        ),
        tenants=tenant_responses,
        active_tenant_id=payload.get("active_tenant_id"),
    )


@router.post("/select-tenant", response_model=SelectTenantResponse)
async def select_tenant(
    payload: SelectTenantRequest,
    authorization: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
):
    """Validate requested tenant_id and verify active database membership before issuing updated active-tenant JWT token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise AppException(
            code="UNAUTHORIZED",
            message="Authentication required",
            status_code=401,
        )

    token = authorization.split(" ", 1)[1]
    token_payload = await verify_and_decode_token(token)
    if not token_payload or "tenant_ids" not in token_payload or "sub" not in token_payload:
        raise AppException(
            code="SESSION_EXPIRED",
            message="Your session has expired. Please sign in again.",
            status_code=401,
        )

    if payload.tenant_id not in token_payload["tenant_ids"]:
        raise AppException(
            code="FORBIDDEN_TENANT_ACCESS",
            message="You are not authorized to access this business",
            status_code=403,
        )

    # Verify tenant exists and is active in DB
    try:
        tenant_uuid = uuid.UUID(payload.tenant_id)
    except ValueError:
        raise AppException(
            code="INVALID_TENANT_ID",
            message="Invalid tenant ID format",
            status_code=400,
        )

    tenant = await db.get(Tenant, tenant_uuid)
    if not tenant or not tenant.is_active:
        raise AppException(
            code="TENANT_INACTIVE",
            message="Requested business is inactive or unavailable",
            status_code=403,
        )

    # Verify active User membership in requested tenant from DB truth
    user_stmt = select(User).where(
        User.email == token_payload["sub"],
        User.tenant_id == tenant_uuid,
        User.is_active == True,
    )
    user_result = await db.execute(user_stmt)
    active_user_record = user_result.scalars().first()

    if not active_user_record:
        raise AppException(
            code="FORBIDDEN_TENANT_ACCESS",
            message="Your membership for this business is inactive or revoked",
            status_code=403,
        )

    # Issue updated access token bound to the selected active_tenant_id and active user_id
    new_token_payload = {
        "sub": token_payload["sub"],
        "user_id": str(active_user_record.id),
        "tenant_ids": token_payload["tenant_ids"],
        "active_tenant_id": str(tenant.id),
        "jti": str(uuid.uuid4()),
    }
    updated_token = create_access_token(new_token_payload)

    # Revoke old token in Redis using old token's exp timestamp
    if token_payload.get("jti"):
        await revoke_token_redis(token_payload["jti"], exp_timestamp=token_payload.get("exp"))

    return SelectTenantResponse(
        access_token=updated_token,
        active_tenant_id=str(tenant.id),
    )


@router.post("/logout")
async def logout(authorization: Optional[str] = Header(None)):
    """Logout user and revoke active server-side JWT token in Redis using token's exp timestamp."""
    if authorization and authorization.startswith("Bearer "):
        token = authorization.split(" ", 1)[1]
        payload = await verify_and_decode_token(token)
        if payload and payload.get("jti"):
            await revoke_token_redis(payload["jti"], exp_timestamp=payload.get("exp"))

    return {"message": "Logged out successfully"}
