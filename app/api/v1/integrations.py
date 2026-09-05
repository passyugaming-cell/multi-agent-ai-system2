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
