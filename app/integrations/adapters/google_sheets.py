import uuid
import logging
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.integrations.exceptions import (
    PermanentIntegrationError,
)
from app.database.models.order import Order

logger = logging.getLogger(__name__)


class GoogleSheetsAdapter:
    """Provider adapter for Google Sheets API operations with mock/fake client support."""

    provider_key = "google_sheets"

    async def connect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        service_account = credentials.get("service_account_json") or credentials.get("oauth_token") or credentials.get("api_key")
        if not service_account:
            raise PermanentIntegrationError("Google Sheets requires service_account_json, oauth_token, or api_key", error_code="INVALID_CREDENTIALS")
        return True

    async def disconnect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> bool:
        return True

    async def health_check(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> bool:
        return bool(credentials.get("service_account_json") or credentials.get("oauth_token") or credentials.get("api_key"))

    async def execute(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        operation: str,
        params: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        spreadsheet_id = params.get("spreadsheet_id")
        if not spreadsheet_id:
            raise PermanentIntegrationError("Missing spreadsheet_id parameter", error_code="MISSING_SPREADSHEET_ID")

        if operation == "read_range":
            range_name = params.get("range", "Sheet1!A1:Z100")
            return {
                "status": "success",
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
                "values": params.get("mock_values", [["Header1", "Header2"], ["Val1", "Val2"]]),
            }

        elif operation == "append_rows":
            range_name = params.get("range", "Sheet1!A1")
            rows = params.get("rows", [])
            return {
                "status": "success",
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
                "updated_rows": len(rows),
                "appended_values": rows,
            }

        elif operation == "update_rows":
            range_name = params.get("range", "Sheet1!A1")
            rows = params.get("rows", [])
            return {
                "status": "success",
                "spreadsheet_id": spreadsheet_id,
                "range": range_name,
                "updated_cells": len(rows) * 5,
            }

        elif operation == "export_orders":
            if not session:
                raise PermanentIntegrationError("Database session required for order export", error_code="MISSING_SESSION")

            stmt = select(Order).where(Order.tenant_id == tenant_id).limit(100)
            orders = list((await session.execute(stmt)).scalars().all())

            header = ["Order ID", "Customer ID", "Status", "Total", "Currency", "Created At"]
            rows = [header]
            for order in orders:
                rows.append([
                    str(order.id),
                    str(order.customer_id) if order.customer_id else "",
                    order.status,
                    str(order.total),
                    order.currency,
                    order.created_at.isoformat() if order.created_at else "",
                ])

            return {
                "status": "success",
                "spreadsheet_id": spreadsheet_id,
                "exported_orders_count": len(orders),
                "rows_appended": len(rows),
            }

        else:
            raise PermanentIntegrationError(f"Unsupported Google Sheets operation: {operation}", error_code="INVALID_OPERATION")

    async def normalize_event(
        self,
        event_type: str,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "event_type": f"google_sheets.{event_type}",
            "payload": raw_payload,
        }
