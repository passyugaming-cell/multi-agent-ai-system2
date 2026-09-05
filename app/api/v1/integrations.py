import uuid
import logging
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_db
from app.integrations.service import IntegrationService
from app.integrations.schemas import (
    IntegrationResponse,
    IntegrationConnectionCreate,
    IntegrationConnectionResponse,
    OperationExecutionRequest,
    OperationExecutionResult,
)
from app.integrations.exceptions import IntegrationError, PermissionDeniedError
from app.integrations.permissions import (
    VIEW_INTEGRATIONS,
    MANAGE_INTEGRATIONS,
    MANAGE_CREDENTIALS,
    EXECUTE_INTEGRATION,
)
from app.integrations.oauth import generate_oauth_state, validate_oauth_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations", tags=["Integrations"])


def get_tenant_id_from_header(x_tenant_id: str = Header(...)) -> uuid.UUID:
    try:
        return uuid.UUID(x_tenant_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-Tenant-ID header must be a valid UUID",
        )


def get_actor_permissions(x_actor_permissions: str | None = Header(None)) -> set[str] | None:
    """Extract actor permissions from header if available."""
    if x_actor_permissions:
        return {p.strip() for p in x_actor_permissions.split(",") if p.strip()}
    return None


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        return await service.list_integrations(tenant_id, actor_permissions=permissions)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.post("/connect/{integration_key}", response_model=IntegrationConnectionResponse)
async def connect_integration(
    integration_key: str,
    payload: IntegrationConnectionCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        conn = await service.connect_integration(
            tenant_id=tenant_id,
            integration_key=integration_key,
            credentials=payload.credentials,
            external_account_id=payload.external_account_id,
            config=payload.meta_data,
            actor_permissions=permissions,
        )
        return conn
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# Dedicated Google Calendar API Endpoints
@router.get("/google-calendar/authorize")
async def google_calendar_authorize(
    redirect_uri: str | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
) -> dict[str, str]:
    if permissions is not None and MANAGE_INTEGRATIONS not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: MANAGE_INTEGRATIONS required")

    from app.core.config import settings
    client_id = settings.GOOGLE_CLIENT_ID
    state = generate_oauth_state(tenant_id=tenant_id, redirect_uri=redirect_uri)
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={client_id}&redirect_uri={redirect_uri or 'http://localhost/callback'}&scope=https://www.googleapis.com/auth/calendar&state={state}&access_type=offline&prompt=consent"
    return {"authorization_url": auth_url, "state": state}


@router.get("/google-calendar/callback")
async def google_calendar_callback(
    code: str,
    state: str,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        validate_oauth_state(state, expected_tenant_id=tenant_id)
        conn = await service.connect_integration(
            tenant_id=tenant_id,
            integration_key="google_calendar",
            credentials={
                "access_token": f"mock_access_token_{code}",
                "refresh_token": f"mock_refresh_token_{code}",
            },
            actor_permissions=permissions,
        )
        return {"status": "success", "connection_id": str(conn.id), "integration_status": conn.status}
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/google-calendar/calendars")
async def google_calendar_list_calendars(
    connection_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="list_calendars",
            params={},
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/google-calendar/events")
async def google_calendar_list_events(
    connection_id: uuid.UUID,
    calendar_id: str = "primary",
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="list_events",
            params={"calendar_id": calendar_id},
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/google-calendar/events/{event_id}")
async def google_calendar_get_event(
    connection_id: uuid.UUID,
    event_id: str,
    calendar_id: str = "primary",
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="get_event",
            params={"calendar_id": calendar_id, "event_id": event_id},
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch("/google-calendar/events/{event_id}")
async def google_calendar_update_event(
    connection_id: uuid.UUID,
    event_id: str,
    payload: dict[str, Any],
    calendar_id: str = "primary",
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        params = {**payload, "event_id": event_id, "calendar_id": calendar_id}
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="update_event",
            params=params,
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete("/google-calendar/events/{event_id}")
async def google_calendar_delete_event(
    connection_id: uuid.UUID,
    event_id: str,
    calendar_id: str = "primary",
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="delete_event",
            params={"calendar_id": calendar_id, "event_id": event_id},
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/google-calendar/events")
async def google_calendar_create_event(
    connection_id: uuid.UUID,
    payload: dict[str, Any],
    idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="create_event",
            params=payload,
            idempotency_key=idempotency_key,
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/google-calendar/availability")
async def google_calendar_check_availability(
    connection_id: uuid.UUID,
    payload: dict[str, Any],
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="check_availability",
            params=payload,
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/connections/{connection_id}/disconnect", response_model=IntegrationConnectionResponse)
async def disconnect_integration(
    connection_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        return await service.disconnect_integration(tenant_id, connection_id, actor_permissions=permissions)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/connections/{connection_id}/execute", response_model=OperationExecutionResult)
async def execute_operation(
    connection_id: uuid.UUID,
    payload: OperationExecutionRequest,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] | None = Depends(get_actor_permissions),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        return await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation=payload.operation,
            params=payload.params,
            idempotency_key=payload.idempotency_key,
            correlation_id=payload.correlation_id,
            actor_permissions=permissions,
        )
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
