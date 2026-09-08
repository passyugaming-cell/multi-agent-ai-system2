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
    MANAGE_PAYMENTS,
    VIEW_PAYMENT_STATUS,
    REQUEST_REFUND,
)
from app.billing.payments import PaymentService
from app.billing.refunds import RefundService
from app.integrations.oauth import generate_oauth_state, validate_oauth_state
from app.core.auth import resolve_actor_permissions

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


def _resolve_permissions_server(actor_perms: set[str] = Depends(resolve_actor_permissions)) -> set[str]:
    return actor_perms


@router.get("", response_model=list[IntegrationResponse])
async def list_integrations(
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        return await service.list_integrations(tenant_id, actor_permissions=permissions)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.get("/connections", response_model=list[IntegrationConnectionResponse])
async def list_tenant_connections(
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        return await service.list_tenant_connections(tenant_id, actor_permissions=permissions)
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))


@router.post("/connect/{integration_key}", response_model=IntegrationConnectionResponse)
async def connect_integration(
    integration_key: str,
    payload: IntegrationConnectionCreate,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
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
    permissions: set[str] = Depends(_resolve_permissions_server),
) -> dict[str, str]:
    if permissions is None or MANAGE_INTEGRATIONS not in permissions:
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
    redirect_uri: str | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if permissions is None or MANAGE_INTEGRATIONS not in permissions or MANAGE_CREDENTIALS not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: MANAGE_INTEGRATIONS and MANAGE_CREDENTIALS required")

    import httpx
    from app.core.config import settings
    service = IntegrationService(db)
    try:
        validate_oauth_state(state, expected_tenant_id=tenant_id)

        token_payload = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri or "http://localhost/callback",
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post("https://oauth2.googleapis.com/token", data=token_payload)
            if resp.status_code != 200:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"OAuth code exchange failed: {resp.text}")
            tokens = resp.json()

        conn = await service.connect_integration(
            tenant_id=tenant_id,
            integration_key="google_calendar",
            credentials={
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "expires_in": tokens.get("expires_in"),
                "token_type": tokens.get("token_type"),
            },
            actor_permissions=permissions,
        )
        return {"status": "success", "connection_id": str(conn.id), "integration_status": conn.status}
    except HTTPException:
        raise
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/google-calendar/calendars")
async def google_calendar_list_calendars(
    connection_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
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
    permissions: set[str] = Depends(_resolve_permissions_server),
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
    permissions: set[str] = Depends(_resolve_permissions_server),
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
    permissions: set[str] = Depends(_resolve_permissions_server),
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
    permissions: set[str] = Depends(_resolve_permissions_server),
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
    permissions: set[str] = Depends(_resolve_permissions_server),
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
    permissions: set[str] = Depends(_resolve_permissions_server),
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


# Dedicated Google Sheets API Endpoints
@router.get("/google-sheets/authorize")
async def google_sheets_authorize(
    redirect_uri: str | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
) -> dict[str, str]:
    if permissions is None or MANAGE_INTEGRATIONS not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: MANAGE_INTEGRATIONS required")

    from app.core.config import settings
    client_id = settings.GOOGLE_CLIENT_ID
    state = generate_oauth_state(tenant_id=tenant_id, redirect_uri=redirect_uri)
    scope = "https://www.googleapis.com/auth/spreadsheets https://www.googleapis.com/auth/drive.readonly"
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={client_id}&redirect_uri={redirect_uri or 'http://localhost/callback'}&scope={scope}&state={state}&access_type=offline&prompt=consent"
    return {"authorization_url": auth_url, "state": state}


@router.get("/google-sheets/callback")
async def google_sheets_callback(
    code: str,
    state: str,
    redirect_uri: str | None = None,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if permissions is None or MANAGE_INTEGRATIONS not in permissions or MANAGE_CREDENTIALS not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: MANAGE_INTEGRATIONS and MANAGE_CREDENTIALS required")

    import httpx
    from app.core.config import settings
    service = IntegrationService(db)
    try:
        validate_oauth_state(state, expected_tenant_id=tenant_id)

        token_payload = {
            "code": code,
            "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri or "http://localhost/callback",
            "grant_type": "authorization_code",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post("https://oauth2.googleapis.com/token", data=token_payload)
            if resp.status_code != 200:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"OAuth code exchange failed: {resp.text}")
            tokens = resp.json()

        conn = await service.connect_integration(
            tenant_id=tenant_id,
            integration_key="google_sheets",
            credentials={
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "expires_in": tokens.get("expires_in"),
                "token_type": tokens.get("token_type"),
            },
            actor_permissions=permissions,
        )
        return {"status": "success", "connection_id": str(conn.id), "integration_status": conn.status}
    except HTTPException:
        raise
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/google-sheets/spreadsheets")
async def google_sheets_list_spreadsheets(
    connection_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="list_spreadsheets",
            params={},
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/google-sheets/spreadsheets/{spreadsheet_id}")
async def google_sheets_get_spreadsheet(
    spreadsheet_id: str,
    connection_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="get_spreadsheet",
            params={"spreadsheet_id": spreadsheet_id},
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/google-sheets/spreadsheets/{spreadsheet_id}/values")
async def google_sheets_read_values(
    spreadsheet_id: str,
    connection_id: uuid.UUID,
    range: str = "Sheet1!A1:Z100",
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="read_values",
            params={"spreadsheet_id": spreadsheet_id, "range": range},
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/google-sheets/spreadsheets/{spreadsheet_id}/append")
async def google_sheets_append_values(
    spreadsheet_id: str,
    connection_id: uuid.UUID,
    payload: dict[str, Any],
    idempotency_key: str | None = Header(None, alias="X-Idempotency-Key"),
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        params = {**payload, "spreadsheet_id": spreadsheet_id}
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="append_values",
            params=params,
            idempotency_key=idempotency_key,
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.put("/google-sheets/spreadsheets/{spreadsheet_id}/values")
async def google_sheets_update_values(
    spreadsheet_id: str,
    connection_id: uuid.UUID,
    payload: dict[str, Any],
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    service = IntegrationService(db)
    try:
        params = {**payload, "spreadsheet_id": spreadsheet_id}
        res = await service.execute_operation(
            tenant_id=tenant_id,
            connection_id=connection_id,
            operation="update_values",
            params=params,
            actor_permissions=permissions,
        )
        return res.result
    except PermissionDeniedError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except IntegrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


# Dedicated Midtrans Payment Gateway Endpoints
@router.post("/midtrans/payments")
async def midtrans_create_payment(
    payload: dict[str, Any],
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if permissions is not None and MANAGE_PAYMENTS not in permissions and MANAGE_INTEGRATIONS not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: MANAGE_PAYMENTS required")

    invoice_id_str = payload.get("invoice_id") or payload.get("order_id")
    if not invoice_id_str:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="invoice_id is required")

    try:
        invoice_id = uuid.UUID(invoice_id_str)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid invoice_id UUID")

    service = IntegrationService(db)
    conn = await service.get_connection_by_provider(tenant_id, "midtrans", allow_internal=True)
    if not conn:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Midtrans integration is not connected for this tenant.")

    from app.billing.invoices import InvoiceService
    from decimal import Decimal
    inv_service = InvoiceService(db)
    invoice = await inv_service.get_invoice(tenant_id, invoice_id)

    pay_service = PaymentService(db)
    amount = Decimal(str(payload.get("amount"))) if payload.get("amount") else invoice.total

    payment = await pay_service.create_payment_intent(
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        amount=amount,
    )
    return {
        "payment_id": str(payment.id),
        "invoice_id": str(payment.invoice_id),
        "status": payment.status,
        "amount": str(payment.amount),
        "provider_payment_id": payment.provider_payment_id,
    }


@router.get("/midtrans/payments/{payment_id}")
async def midtrans_get_payment_status(
    payment_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if permissions is not None and VIEW_PAYMENT_STATUS not in permissions and VIEW_INTEGRATIONS not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: VIEW_PAYMENT_STATUS required")

    from app.billing.exceptions import PaymentFailedError
    from app.core.exceptions import AppError
    pay_service = PaymentService(db)
    try:
        payment = await pay_service.get_payment(tenant_id, payment_id)
    except (PaymentFailedError, AppError, Exception):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    return {
        "payment_id": str(payment.id),
        "invoice_id": str(payment.invoice_id),
        "status": payment.status,
        "amount": str(payment.amount),
        "provider_payment_id": payment.provider_payment_id,
        "payment_method": getattr(payment, "payment_method", payment.provider),
    }


@router.post("/midtrans/payments/{payment_id}/cancel")
async def midtrans_cancel_payment(
    payment_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if permissions is not None and MANAGE_PAYMENTS not in permissions and MANAGE_INTEGRATIONS not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: MANAGE_PAYMENTS required")

    from app.billing.exceptions import PaymentFailedError
    from app.core.exceptions import AppError
    pay_service = PaymentService(db)
    try:
        payment = await pay_service.get_payment(tenant_id, payment_id)
    except (PaymentFailedError, AppError, Exception):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    service = IntegrationService(db)
    conn = await service.get_connection_by_provider(tenant_id, "midtrans", allow_internal=True)
    if not conn:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Midtrans connection not active")

    res = await service.execute_operation(
        tenant_id=tenant_id,
        connection_id=conn.id,
        operation="cancel_payment",
        params={"order_id": payment.provider_payment_id or str(payment.invoice_id)},
        actor_permissions={EXECUTE_INTEGRATION},
    )

    if res.result and res.result.get("success"):
        payment.status = "CANCELLED"
        await db.commit()

    return {"status": "CANCELLED" if (res.result and res.result.get("success")) else payment.status, "result": res.result}


@router.post("/midtrans/payments/{payment_id}/refund")
async def midtrans_refund_payment(
    payment_id: uuid.UUID,
    payload: dict[str, Any],
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
    db: AsyncSession = Depends(get_db),
) -> Any:
    if permissions is not None and REQUEST_REFUND not in permissions and MANAGE_INTEGRATIONS not in permissions:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: REQUEST_REFUND required")

    from app.billing.exceptions import PaymentFailedError
    from app.core.exceptions import AppError
    pay_service = PaymentService(db)
    try:
        payment = await pay_service.get_payment(tenant_id, payment_id)
    except (PaymentFailedError, AppError, Exception):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    from decimal import Decimal
    amount_str = payload.get("amount")
    amount = Decimal(str(amount_str)) if amount_str else payment.amount
    reason = payload.get("reason", "Refund requested")

    refund_service = RefundService(db)
    try:
        refund_req = await refund_service.request_refund(
            tenant_id=tenant_id,
            payment_id=payment_id,
            amount=amount,
            reason=reason,
        )
    except (PaymentFailedError, AppError, Exception) as exc:
        if "not found" in str(exc).lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    from app.database.models.workflow import Approval
    appr = Approval(
        tenant_id=tenant_id,
        requested_by="api_user",
        action_type="refund_payment",
        target=f"payment_{payment_id}",
        reason=reason,
        risk_level="HIGH",
        status="PENDING",
        meta_data={
            "refund_request_id": str(refund_req.id),
            "payment_id": str(payment_id),
            "amount": str(amount),
            "provider": "MIDTRANS",
        },
    )
    db.add(appr)
    await db.commit()
    await db.refresh(appr)

    return {
        "status": "APPROVAL_REQUIRED",
        "refund_request_id": str(refund_req.id),
        "approval_id": str(appr.id),
        "amount": str(amount),
    }


@router.post("/connections/{connection_id}/disconnect", response_model=IntegrationConnectionResponse)
async def disconnect_integration(
    connection_id: uuid.UUID,
    tenant_id: uuid.UUID = Depends(get_tenant_id_from_header),
    permissions: set[str] = Depends(_resolve_permissions_server),
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
    permissions: set[str] = Depends(_resolve_permissions_server),
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
