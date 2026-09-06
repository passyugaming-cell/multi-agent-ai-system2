import uuid
import logging
import httpx
from typing import Any
from urllib.parse import quote
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import settings
from app.integrations.exceptions import (
    PermanentIntegrationError,
    TransientIntegrationError,
)
from app.integrations.registry import integration_registry
from app.integrations.credentials import redact_secrets

logger = logging.getLogger(__name__)

GOOGLE_SHEETS_BASE_URL = "https://sheets.googleapis.com/v4/spreadsheets"
GOOGLE_DRIVE_BASE_URL = "https://www.googleapis.com/drive/v3"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"

# Selected Google OAuth scopes required for Google Sheets Provider (least privilege)
GOOGLE_SHEETS_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]


class GoogleSheetsAdapter:
    """Provider adapter for Google Sheets API operations with real HTTP client, OAuth 2.0 token refresh, real connectivity health check, spreadsheet discovery, values read/append/update, and error normalization."""

    provider_key = "google_sheets"

    async def _get_authenticated_client(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> tuple[httpx.AsyncClient, dict[str, str]]:
        access_token = credentials.get("access_token")
        refresh_token = credentials.get("refresh_token")
        api_key = credentials.get("api_key")

        # Refresh access token if expired/missing when refresh_token is available
        if not access_token and refresh_token:
            access_token = await self._refresh_access_token(tenant_id, connection_id, refresh_token, session)

        if not access_token and not api_key:
            raise PermanentIntegrationError(
                "Google Sheets requires valid OAuth credentials (access_token or refresh_token) or api_key",
                error_code="AUTHENTICATION_ERROR",
            )

        client = httpx.AsyncClient(timeout=15.0)
        headers = {}
        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        return client, headers

    async def _refresh_access_token(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        refresh_token: str,
        session: AsyncSession | None = None,
    ) -> str:
        client_id = settings.GOOGLE_CLIENT_ID
        client_secret = settings.GOOGLE_CLIENT_SECRET

        payload = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                resp = await client.post(GOOGLE_TOKEN_URL, data=payload)
                if resp.status_code != 200:
                    raise PermanentIntegrationError("Token refresh failed", error_code="AUTHENTICATION_ERROR")
                data = resp.json()
                new_access_token = data.get("access_token")

                if session and new_access_token:
                    from app.database.models.integrations import IntegrationCredential
                    from app.integrations.credentials import CredentialVault
                    vault = CredentialVault()
                    stmt = select(IntegrationCredential).where(
                        and_(
                            IntegrationCredential.tenant_id == tenant_id,
                            IntegrationCredential.connection_id == connection_id,
                        )
                    )
                    cred = (await session.execute(stmt)).scalar_one_or_none()
                    if cred:
                        cred_dict = vault.decrypt_credentials(cred.encrypted_secret)
                        cred_dict["access_token"] = new_access_token
                        cred.encrypted_secret = vault.encrypt_credentials(cred_dict)
                        await session.flush()

                return new_access_token
            except PermanentIntegrationError:
                raise
            except Exception as e:
                raise PermanentIntegrationError(f"Failed to refresh Google OAuth token: {redact_secrets(str(e))}", error_code="AUTHENTICATION_ERROR")

    async def connect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        from app.integrations.events import publish_integration_event
        access_token = credentials.get("access_token")
        refresh_token = credentials.get("refresh_token")
        api_key = credentials.get("api_key")

        if not (access_token or refresh_token or api_key):
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="integration.google_sheets.connection_failed",
                payload={"connection_id": str(connection_id), "reason": "Missing OAuth tokens or API key"},
            )
            raise PermanentIntegrationError(
                "Google Sheets requires access_token, refresh_token, or api_key",
                error_code="INVALID_CREDENTIALS",
            )

        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="integration.google_sheets.connected",
            payload={"connection_id": str(connection_id)},
        )
        return True

    async def disconnect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> bool:
        from app.integrations.events import publish_integration_event
        logger.info("Disconnecting Google Sheets for tenant %s connection %s", tenant_id, connection_id)
        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="integration.google_sheets.disconnected",
            payload={"connection_id": str(connection_id)},
        )
        return True

    async def health_check(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> bool:
        """Performs a real authenticated Google API connectivity check to verify provider health."""
        if not (credentials.get("access_token") or credentials.get("refresh_token") or credentials.get("api_key")):
            return False

        try:
            client, headers = await self._get_authenticated_client(tenant_id, connection_id, credentials, session)
            try:
                # Issue lightweight drive files list query to verify credentials & network reachability
                url = f"{GOOGLE_DRIVE_BASE_URL}/files"
                resp = await client.get(url, headers=headers, params={"pageSize": 1, "fields": "files(id)"})
                return resp.status_code == 200
            finally:
                await client.aclose()
        except Exception as e:
            logger.warning("Health check failed for Google Sheets connection %s: %s", connection_id, redact_secrets(str(e)))
            return False

    async def execute(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        operation: str,
        params: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        try:
            res = await self._execute_internal(tenant_id, connection_id, credentials, operation, params, session)
            from app.integrations.events import publish_integration_event
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="integration.google_sheets.operation_succeeded",
                payload={"connection_id": str(connection_id), "operation": operation},
            )
            return res
        except PermanentIntegrationError as e:
            if e.error_code == "AUTHENTICATION_ERROR" and credentials.get("refresh_token"):
                # Single bounded retry after token refresh
                refresh_token = credentials["refresh_token"]
                new_token = await self._refresh_access_token(tenant_id, connection_id, refresh_token, session)
                credentials["access_token"] = new_token
                try:
                    res = await self._execute_internal(tenant_id, connection_id, credentials, operation, params, session)
                    from app.integrations.events import publish_integration_event
                    await publish_integration_event(
                        tenant_id=tenant_id,
                        event_type="integration.google_sheets.operation_succeeded",
                        payload={"connection_id": str(connection_id), "operation": operation},
                    )
                    return res
                except Exception as retry_exc:
                    from app.integrations.events import publish_integration_event
                    await publish_integration_event(
                        tenant_id=tenant_id,
                        event_type="integration.google_sheets.operation_failed",
                        payload={"connection_id": str(connection_id), "operation": operation, "error": redact_secrets(str(retry_exc))},
                    )
                    raise retry_exc

            from app.integrations.events import publish_integration_event
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="integration.google_sheets.operation_failed",
                payload={"connection_id": str(connection_id), "operation": operation, "error": redact_secrets(str(e))},
            )
            raise e
        except Exception as e:
            from app.integrations.events import publish_integration_event
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="integration.google_sheets.operation_failed",
                payload={"connection_id": str(connection_id), "operation": operation, "error": redact_secrets(str(e))},
            )
            raise e

    async def _execute_internal(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        operation: str,
        params: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        client, headers = await self._get_authenticated_client(tenant_id, connection_id, credentials, session)

        try:
            if operation in ("get_spreadsheet", "get_metadata"):
                spreadsheet_id = params.get("spreadsheet_id")
                if not spreadsheet_id:
                    raise PermanentIntegrationError("Missing spreadsheet_id parameter", error_code="MISSING_SPREADSHEET_ID")

                encoded_id = quote(str(spreadsheet_id), safe="")
                url = f"{GOOGLE_SHEETS_BASE_URL}/{encoded_id}"
                resp = await client.get(url, headers=headers)
                self._handle_http_error(resp)
                data = resp.json()

                sheets_metadata = []
                for s in data.get("sheets", []):
                    props = s.get("properties", {})
                    sheets_metadata.append({
                        "sheet_id": props.get("sheetId"),
                        "title": props.get("title"),
                        "index": props.get("index"),
                        "sheet_type": props.get("sheetType", "GRID"),
                        "grid_properties": props.get("gridProperties", {}),
                    })

                return {
                    "status": "success",
                    "spreadsheet_id": str(spreadsheet_id),
                    "title": data.get("properties", {}).get("title"),
                    "locale": data.get("properties", {}).get("locale"),
                    "time_zone": data.get("properties", {}).get("timeZone"),
                    "sheets": sheets_metadata,
                }

            elif operation in ("read_values", "read_range"):
                spreadsheet_id = params.get("spreadsheet_id")
                if not spreadsheet_id:
                    raise PermanentIntegrationError("Missing spreadsheet_id parameter", error_code="MISSING_SPREADSHEET_ID")

                range_name = params.get("range", "Sheet1!A1:Z100")
                encoded_id = quote(str(spreadsheet_id), safe="")
                encoded_range = quote(str(range_name), safe="!:$")

                url = f"{GOOGLE_SHEETS_BASE_URL}/{encoded_id}/values/{encoded_range}"
                resp = await client.get(url, headers=headers)
                self._handle_http_error(resp)
                data = resp.json()

                return {
                    "status": "success",
                    "spreadsheet_id": str(spreadsheet_id),
                    "range": data.get("range", range_name),
                    "major_dimension": data.get("majorDimension", "ROWS"),
                    "values": data.get("values", []),
                }

            elif operation in ("append_values", "append_rows"):
                spreadsheet_id = params.get("spreadsheet_id")
                if not spreadsheet_id:
                    raise PermanentIntegrationError("Missing spreadsheet_id parameter", error_code="MISSING_SPREADSHEET_ID")

                range_name = params.get("range", "Sheet1!A1")
                rows = params.get("values") or params.get("rows") or []
                encoded_id = quote(str(spreadsheet_id), safe="")
                encoded_range = quote(str(range_name), safe="!:$")

                url = f"{GOOGLE_SHEETS_BASE_URL}/{encoded_id}/values/{encoded_range}:append"
                query_params = {"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"}
                body = {
                    "range": range_name,
                    "majorDimension": "ROWS",
                    "values": rows,
                }

                resp = await client.post(url, headers=headers, params=query_params, json=body)
                self._handle_http_error(resp)
                data = resp.json()

                updates = data.get("updates", {})
                return {
                    "status": "success",
                    "spreadsheet_id": str(spreadsheet_id),
                    "table_range": updates.get("tableRange"),
                    "updated_range": updates.get("updatedRange"),
                    "updated_rows": updates.get("updatedRows", len(rows)),
                    "updated_columns": updates.get("updatedColumns", 0),
                    "updated_cells": updates.get("updatedCells", 0),
                    "appended_values": rows,
                }

            elif operation in ("update_values", "update_rows"):
                spreadsheet_id = params.get("spreadsheet_id")
                if not spreadsheet_id:
                    raise PermanentIntegrationError("Missing spreadsheet_id parameter", error_code="MISSING_SPREADSHEET_ID")

                range_name = params.get("range", "Sheet1!A1")
                rows = params.get("values") or params.get("rows") or []
                encoded_id = quote(str(spreadsheet_id), safe="")
                encoded_range = quote(str(range_name), safe="!:$")

                url = f"{GOOGLE_SHEETS_BASE_URL}/{encoded_id}/values/{encoded_range}"
                query_params = {"valueInputOption": "USER_ENTERED"}
                body = {
                    "range": range_name,
                    "majorDimension": "ROWS",
                    "values": rows,
                }

                resp = await client.put(url, headers=headers, params=query_params, json=body)
                self._handle_http_error(resp)
                data = resp.json()

                return {
                    "status": "success",
                    "spreadsheet_id": str(spreadsheet_id),
                    "updated_range": data.get("updatedRange", range_name),
                    "updated_rows": data.get("updatedRows", len(rows)),
                    "updated_columns": data.get("updatedColumns", 0),
                    "updated_cells": data.get("updatedCells", len(rows) * (len(rows[0]) if rows else 0)),
                }

            elif operation == "list_spreadsheets":
                url = f"{GOOGLE_DRIVE_BASE_URL}/files"
                query_params = {
                    "q": "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false",
                    "fields": "files(id, name, createdTime, modifiedTime, webViewLink)",
                }
                resp = await client.get(url, headers=headers, params=query_params)
                self._handle_http_error(resp)
                data = resp.json()

                spreadsheets = [
                    {
                        "id": f.get("id"),
                        "name": f.get("name"),
                        "created_time": f.get("createdTime"),
                        "modified_time": f.get("modifiedTime"),
                        "web_view_link": f.get("webViewLink"),
                    }
                    for f in data.get("files", [])
                ]

                return {
                    "status": "success",
                    "spreadsheets": spreadsheets,
                }

            elif operation == "export_orders":
                spreadsheet_id = params.get("spreadsheet_id")
                if not spreadsheet_id:
                    raise PermanentIntegrationError("Missing spreadsheet_id parameter", error_code="MISSING_SPREADSHEET_ID")

                if not session:
                    raise PermanentIntegrationError("Database session required for order export", error_code="MISSING_SESSION")

                from app.database.models.order import Order
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

                range_name = params.get("range", "Sheet1!A1")
                encoded_id = quote(str(spreadsheet_id), safe="")
                encoded_range = quote(str(range_name), safe="!:$")

                url = f"{GOOGLE_SHEETS_BASE_URL}/{encoded_id}/values/{encoded_range}:append"
                query_params = {"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"}
                body = {
                    "range": range_name,
                    "majorDimension": "ROWS",
                    "values": rows,
                }

                resp = await client.post(url, headers=headers, params=query_params, json=body)
                self._handle_http_error(resp)

                return {
                    "status": "success",
                    "spreadsheet_id": str(spreadsheet_id),
                    "exported_orders_count": len(orders),
                    "rows_appended": len(rows),
                }

            else:
                raise PermanentIntegrationError(f"Unsupported Google Sheets operation: {operation}", error_code="INVALID_OPERATION")

        finally:
            await client.aclose()

    def _handle_http_error(self, resp: httpx.Response) -> None:
        if resp.status_code in (200, 201, 204):
            return
        if resp.status_code == 400:
            raise PermanentIntegrationError("Invalid request or parameters", error_code="INVALID_REQUEST")
        if resp.status_code == 401:
            raise PermanentIntegrationError("Invalid or expired OAuth access token", error_code="AUTHENTICATION_ERROR")
        if resp.status_code == 403:
            raise PermanentIntegrationError("Permission denied by Google API", error_code="AUTHORIZATION_ERROR")
        if resp.status_code == 404:
            raise PermanentIntegrationError("Spreadsheet or range not found on Google Sheets", error_code="NOT_FOUND")
        if resp.status_code == 409:
            raise PermanentIntegrationError("Conflict in Google API request", error_code="CONFLICT")
        if resp.status_code == 429:
            raise TransientIntegrationError("Rate limit exceeded by Google API", error_code="RATE_LIMITED")
        if resp.status_code in (500, 502, 503, 504):
            raise TransientIntegrationError(f"Google Sheets API internal server error ({resp.status_code})", error_code="PROVIDER_ERROR")

        raise PermanentIntegrationError(f"Google API request failed with status {resp.status_code}", error_code="PROVIDER_ERROR")

    async def normalize_event(
        self,
        event_type: str,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "event_type": f"google_sheets.{event_type}",
            "payload": redact_secrets(raw_payload),
        }


# Register adapter globally
integration_registry.register("google_sheets", GoogleSheetsAdapter())
