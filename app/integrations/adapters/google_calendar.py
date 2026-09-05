import uuid
import logging
import zoneinfo
import httpx
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_

from app.core.config import settings
from app.integrations.exceptions import (
    PermanentIntegrationError,
    TransientIntegrationError,
)
from app.integrations.registry import integration_registry

logger = logging.getLogger(__name__)

GOOGLE_CALENDAR_BASE_URL = "https://www.googleapis.com/calendar/v3"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"


def validate_and_parse_datetime(dt_str: str, default_tz: str = "UTC") -> tuple[datetime, str]:
    """Parses an ISO format datetime string and returns (timezone-aware datetime, iana_timezone_name)."""
    if not dt_str:
        raise PermanentIntegrationError("Datetime string cannot be empty", error_code="INVALID_DATETIME")
    try:
        dt = datetime.fromisoformat(dt_str)
    except Exception as e:
        raise PermanentIntegrationError(f"Invalid ISO datetime format '{dt_str}': {e}", error_code="INVALID_DATETIME")

    tz_name = default_tz
    if dt.tzinfo is not None:
        tz_name = getattr(dt.tzinfo, "key", str(dt.tzinfo))
        if tz_name.startswith("UTC+") or tz_name.startswith("UTC-") or tz_name == "UTC":
            tz_name = default_tz
    else:
        try:
            tz = zoneinfo.ZoneInfo(default_tz)
            dt = dt.replace(tzinfo=tz)
        except Exception as e:
            raise PermanentIntegrationError(f"Invalid timezone identifier '{default_tz}': {e}", error_code="INVALID_TIMEZONE")

    return dt, tz_name


class GoogleCalendarAdapter:
    """Provider adapter for Google Calendar API operations with real HTTP client, OAuth token refresh, timezone, freebusy availability, and error normalization."""

    provider_key = "google_calendar"

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

        # Check if we need to refresh access_token
        if not access_token and refresh_token:
            access_token = await self._refresh_access_token(tenant_id, connection_id, refresh_token, session)

        if not access_token and not api_key:
            raise PermanentIntegrationError(
                "Google Calendar requires valid access_token, refresh_token, or api_key",
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
                    raise PermanentIntegrationError(f"Token refresh failed: {resp.text}", error_code="AUTHENTICATION_ERROR")
                data = resp.json()
                new_access_token = data.get("access_token")

                if session and new_access_token:
                    # Update credentials in Vault / DB if session available
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
            except Exception as e:
                raise PermanentIntegrationError(f"Failed to refresh Google OAuth token: {e}", error_code="AUTHENTICATION_ERROR")

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
                event_type="integration.google_calendar.connection_failed",
                payload={"connection_id": str(connection_id), "reason": "Missing credentials"},
            )
            raise PermanentIntegrationError(
                "Google Calendar requires access_token, refresh_token, or api_key",
                error_code="INVALID_CREDENTIALS",
            )

        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="integration.google_calendar.connected",
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
        logger.info("Disconnecting Google Calendar for tenant %s connection %s", tenant_id, connection_id)
        await publish_integration_event(
            tenant_id=tenant_id,
            event_type="integration.google_calendar.disconnected",
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
        return bool(credentials.get("access_token") or credentials.get("refresh_token") or credentials.get("api_key"))

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
            return await self._execute_internal(tenant_id, connection_id, credentials, operation, params, session)
        except PermanentIntegrationError as e:
            if e.error_code == "AUTHENTICATION_ERROR" and credentials.get("refresh_token"):
                # Retry with token refresh
                refresh_token = credentials["refresh_token"]
                new_token = await self._refresh_access_token(tenant_id, connection_id, refresh_token, session)
                credentials["access_token"] = new_token
                try:
                    return await self._execute_internal(tenant_id, connection_id, credentials, operation, params, session)
                except Exception as retry_exc:
                    from app.integrations.events import publish_integration_event
                    await publish_integration_event(
                        tenant_id=tenant_id,
                        event_type="integration.google_calendar.operation_failed",
                        payload={"connection_id": str(connection_id), "operation": operation, "error": str(retry_exc)},
                    )
                    raise retry_exc

            from app.integrations.events import publish_integration_event
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="integration.google_calendar.operation_failed",
                payload={"connection_id": str(connection_id), "operation": operation, "error": str(e)},
            )
            raise e
        except Exception as e:
            from app.integrations.events import publish_integration_event
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="integration.google_calendar.operation_failed",
                payload={"connection_id": str(connection_id), "operation": operation, "error": str(e)},
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
            if operation == "list_calendars":
                url = f"{GOOGLE_CALENDAR_BASE_URL}/users/me/calendarList"
                resp = await client.get(url, headers=headers)
                self._handle_http_error(resp)
                data = resp.json()
                return {"status": "success", "calendars": data.get("items", [])}

            elif operation == "get_calendar":
                calendar_id = params.get("calendar_id", "primary")
                url = f"{GOOGLE_CALENDAR_BASE_URL}/calendars/{calendar_id}"
                resp = await client.get(url, headers=headers)
                self._handle_http_error(resp)
                data = resp.json()
                return {"status": "success", "id": data.get("id"), "summary": data.get("summary"), "timeZone": data.get("timeZone")}

            elif operation == "list_events":
                calendar_id = params.get("calendar_id", "primary")
                url = f"{GOOGLE_CALENDAR_BASE_URL}/calendars/{calendar_id}/events"
                query_params = {}
                if "time_min" in params:
                    query_params["timeMin"] = params["time_min"]
                if "time_max" in params:
                    query_params["timeMax"] = params["time_max"]

                resp = await client.get(url, headers=headers, params=query_params)
                self._handle_http_error(resp)
                data = resp.json()
                return {"status": "success", "calendar_id": calendar_id, "events": data.get("items", [])}

            elif operation == "get_event":
                calendar_id = params.get("calendar_id", "primary")
                event_id = params.get("event_id")
                if not event_id:
                    raise PermanentIntegrationError("Missing event_id", error_code="VALIDATION_ERROR")

                url = f"{GOOGLE_CALENDAR_BASE_URL}/calendars/{calendar_id}/events/{event_id}"
                resp = await client.get(url, headers=headers)
                self._handle_http_error(resp)
                data = resp.json()
                return {"status": "success", "event": data}

            elif operation == "check_availability":
                time_min_str = params.get("time_min")
                time_max_str = params.get("time_max")
                tz_str = params.get("timezone", "Asia/Jakarta")

                if not time_min_str or not time_max_str:
                    raise PermanentIntegrationError("check_availability requires time_min and time_max", error_code="VALIDATION_ERROR")

                dt_min, _ = validate_and_parse_datetime(time_min_str, tz_str)
                dt_max, _ = validate_and_parse_datetime(time_max_str, tz_str)

                if dt_min >= dt_max:
                    raise PermanentIntegrationError("time_min must be earlier than time_max", error_code="VALIDATION_ERROR")

                calendar_id = params.get("calendar_id", "primary")
                url = f"{GOOGLE_CALENDAR_BASE_URL}/freeBusy"
                request_body = {
                    "timeMin": dt_min.isoformat(),
                    "timeMax": dt_max.isoformat(),
                    "timeZone": tz_str,
                    "items": [{"id": calendar_id}],
                }

                resp = await client.post(url, headers=headers, json=request_body)
                self._handle_http_error(resp)
                data = resp.json()

                calendars_busy = data.get("calendars", {}).get(calendar_id, {}).get("busy", [])
                is_available = len(calendars_busy) == 0

                return {
                    "status": "success",
                    "available": is_available,
                    "timezone": tz_str,
                    "time_min": dt_min.isoformat(),
                    "time_max": dt_max.isoformat(),
                    "busy_periods": calendars_busy,
                }

            elif operation == "create_event":
                calendar_id = params.get("calendar_id", "primary")
                summary = params.get("summary")
                start_data = params.get("start")
                end_data = params.get("end")

                if not summary:
                    raise PermanentIntegrationError("Missing event summary", error_code="VALIDATION_ERROR")
                if not start_data or not end_data:
                    raise PermanentIntegrationError("Missing event start or end times", error_code="VALIDATION_ERROR")

                start_dt_str = start_data.get("dateTime") if isinstance(start_data, dict) else str(start_data)
                end_dt_str = end_data.get("dateTime") if isinstance(end_data, dict) else str(end_data)
                tz_str = (start_data.get("timeZone") if isinstance(start_data, dict) else None) or params.get("timezone", "Asia/Jakarta")

                dt_start, tz_start = validate_and_parse_datetime(start_dt_str, tz_str)
                dt_end, _ = validate_and_parse_datetime(end_dt_str, tz_start)

                if dt_start >= dt_end:
                    raise PermanentIntegrationError("Event start time must be before end time", error_code="VALIDATION_ERROR")

                event_body = {
                    "summary": summary,
                    "description": params.get("description", ""),
                    "location": params.get("location", ""),
                    "start": {"dateTime": dt_start.isoformat(), "timeZone": tz_start},
                    "end": {"dateTime": dt_end.isoformat(), "timeZone": tz_start},
                    "attendees": params.get("attendees", []),
                }

                url = f"{GOOGLE_CALENDAR_BASE_URL}/calendars/{calendar_id}/events"
                resp = await client.post(url, headers=headers, json=event_body)
                self._handle_http_error(resp)
                data = resp.json()

                from app.integrations.events import publish_integration_event
                await publish_integration_event(
                    tenant_id=tenant_id,
                    event_type="integration.google_calendar.event_created",
                    payload={"connection_id": str(connection_id), "calendar_id": calendar_id, "event_id": data.get("id")},
                )

                return {
                    "status": "success",
                    "event_id": data.get("id"),
                    "calendar_id": calendar_id,
                    "event": data,
                }

            elif operation == "update_event":
                calendar_id = params.get("calendar_id", "primary")
                event_id = params.get("event_id")
                if not event_id:
                    raise PermanentIntegrationError("Missing event_id for update", error_code="VALIDATION_ERROR")

                url = f"{GOOGLE_CALENDAR_BASE_URL}/calendars/{calendar_id}/events/{event_id}"
                event_body = {}
                if "summary" in params:
                    event_body["summary"] = params["summary"]
                if "description" in params:
                    event_body["description"] = params["description"]
                if "start" in params:
                    start_data = params["start"]
                    start_dt_str = start_data.get("dateTime") if isinstance(start_data, dict) else str(start_data)
                    tz_str = (start_data.get("timeZone") if isinstance(start_data, dict) else None) or "Asia/Jakarta"
                    dt_start, tz_start = validate_and_parse_datetime(start_dt_str, tz_str)
                    event_body["start"] = {"dateTime": dt_start.isoformat(), "timeZone": tz_start}
                if "end" in params:
                    end_data = params["end"]
                    end_dt_str = end_data.get("dateTime") if isinstance(end_data, dict) else str(end_data)
                    tz_str = (end_data.get("timeZone") if isinstance(end_data, dict) else None) or "Asia/Jakarta"
                    dt_end, tz_end = validate_and_parse_datetime(end_dt_str, tz_str)
                    event_body["end"] = {"dateTime": dt_end.isoformat(), "timeZone": tz_end}

                resp = await client.patch(url, headers=headers, json=event_body)
                self._handle_http_error(resp)
                data = resp.json()

                from app.integrations.events import publish_integration_event
                await publish_integration_event(
                    tenant_id=tenant_id,
                    event_type="integration.google_calendar.event_updated",
                    payload={"connection_id": str(connection_id), "calendar_id": calendar_id, "event_id": event_id},
                )

                return {
                    "status": "success",
                    "event_id": event_id,
                    "calendar_id": calendar_id,
                    "event": data,
                }

            elif operation == "delete_event":
                calendar_id = params.get("calendar_id", "primary")
                event_id = params.get("event_id")
                if not event_id:
                    raise PermanentIntegrationError("Missing event_id for delete", error_code="VALIDATION_ERROR")

                url = f"{GOOGLE_CALENDAR_BASE_URL}/calendars/{calendar_id}/events/{event_id}"
                resp = await client.delete(url, headers=headers)
                self._handle_http_error(resp)

                from app.integrations.events import publish_integration_event
                await publish_integration_event(
                    tenant_id=tenant_id,
                    event_type="integration.google_calendar.event_deleted",
                    payload={"connection_id": str(connection_id), "calendar_id": calendar_id, "event_id": event_id},
                )

                return {
                    "status": "success",
                    "deleted": True,
                    "event_id": event_id,
                    "calendar_id": calendar_id,
                }

            else:
                raise PermanentIntegrationError(
                    f"Unsupported Google Calendar operation: {operation}",
                    error_code="INVALID_OPERATION",
                )
        finally:
            await client.aclose()

    def _handle_http_error(self, resp: httpx.Response) -> None:
        if resp.status_code == 200 or resp.status_code == 204:
            return
        if resp.status_code == 401:
            raise PermanentIntegrationError("Invalid or expired OAuth access token", error_code="AUTHENTICATION_ERROR")
        if resp.status_code == 403:
            raise PermanentIntegrationError("Permission denied by Google API", error_code="AUTHORIZATION_ERROR")
        if resp.status_code == 404:
            raise PermanentIntegrationError("Resource not found on Google Calendar", error_code="NOT_FOUND")
        if resp.status_code == 429:
            raise TransientIntegrationError("Rate limit exceeded by Google API", error_code="RATE_LIMITED")
        if resp.status_code >= 500:
            raise TransientIntegrationError(f"Google Calendar API internal server error ({resp.status_code})", error_code="PROVIDER_ERROR")

        raise PermanentIntegrationError(f"Google API request failed: {resp.text}", error_code="PROVIDER_ERROR")

    async def normalize_event(
        self,
        event_type: str,
        raw_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "event_type": f"google_calendar.{event_type}",
            "payload": raw_payload,
        }


# Register adapter globally
integration_registry.register("google_calendar", GoogleCalendarAdapter())
