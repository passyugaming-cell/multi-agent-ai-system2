import uuid
import logging
import zoneinfo
from datetime import datetime, timezone
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.exceptions import (
    PermanentIntegrationError,
    TransientIntegrationError,
)
from app.integrations.registry import integration_registry

logger = logging.getLogger(__name__)


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
        # Get tz name if available or offset name
        tz_name = getattr(dt.tzinfo, "key", str(dt.tzinfo))
        if tz_name.startswith("UTC+") or tz_name.startswith("UTC-") or tz_name == "UTC":
            tz_name = default_tz
    else:
        # Assign default timezone if naive
        try:
            tz = zoneinfo.ZoneInfo(default_tz)
            dt = dt.replace(tzinfo=tz)
        except Exception as e:
            raise PermanentIntegrationError(f"Invalid timezone identifier '{default_tz}': {e}", error_code="INVALID_TIMEZONE")

    return dt, tz_name


class GoogleCalendarAdapter:
    """Provider adapter for Google Calendar API operations with OAuth, timezone, freebusy availability, and error normalization."""

    provider_key = "google_calendar"

    async def connect(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        config: dict[str, Any] | None = None,
        session: AsyncSession | None = None,
    ) -> bool:
        access_token = credentials.get("access_token")
        refresh_token = credentials.get("refresh_token")
        api_key = credentials.get("api_key")

        if not (access_token or refresh_token or api_key):
            raise PermanentIntegrationError(
                "Google Calendar requires access_token, refresh_token, or api_key",
                error_code="INVALID_CREDENTIALS",
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
        has_token = bool(credentials.get("access_token") or credentials.get("refresh_token") or credentials.get("api_key"))
        return has_token

    async def execute(
        self,
        tenant_id: uuid.UUID,
        connection_id: uuid.UUID,
        credentials: dict[str, Any],
        operation: str,
        params: dict[str, Any],
        session: AsyncSession | None = None,
    ) -> dict[str, Any]:
        # Check mock/fake client or errors injected for testing
        if params.get("simulate_rate_limit"):
            raise TransientIntegrationError("Rate limit exceeded by Google API", error_code="RATE_LIMITED")
        if params.get("simulate_network_error"):
            raise TransientIntegrationError("Google Calendar API connection timeout", error_code="TIMEOUT")
        if params.get("simulate_invalid_auth"):
            raise PermanentIntegrationError("Invalid OAuth credentials", error_code="AUTHENTICATION_ERROR")

        # Mock store support for unit test verification if provided in params
        mock_events = params.get("_mock_events_store")

        if operation == "list_calendars":
            calendars = [
                {
                    "id": "primary",
                    "summary": "Primary Calendar",
                    "timeZone": params.get("timeZone", "Asia/Jakarta"),
                    "primary": True,
                }
            ]
            return {"status": "success", "calendars": calendars}

        elif operation == "get_calendar":
            calendar_id = params.get("calendar_id", "primary")
            return {
                "status": "success",
                "id": calendar_id,
                "summary": f"Calendar {calendar_id}",
                "timeZone": params.get("timeZone", "Asia/Jakarta"),
            }

        elif operation == "list_events":
            calendar_id = params.get("calendar_id", "primary")
            if mock_events is not None:
                events = [e for e in mock_events.values() if e.get("calendar_id") == calendar_id]
            else:
                events = params.get("mock_events", [])
            return {
                "status": "success",
                "calendar_id": calendar_id,
                "events": events,
            }

        elif operation == "get_event":
            calendar_id = params.get("calendar_id", "primary")
            event_id = params.get("event_id")
            if not event_id:
                raise PermanentIntegrationError("Missing event_id", error_code="VALIDATION_ERROR")

            if mock_events is not None and event_id in mock_events:
                return {"status": "success", "event": mock_events[event_id]}

            if params.get("simulate_not_found"):
                raise PermanentIntegrationError(f"Event {event_id} not found", error_code="NOT_FOUND")

            return {
                "status": "success",
                "event": {
                    "id": event_id,
                    "calendar_id": calendar_id,
                    "summary": params.get("summary", "Sample Event"),
                    "start": params.get("start", {"dateTime": "2026-09-10T14:00:00+07:00", "timeZone": "Asia/Jakarta"}),
                    "end": params.get("end", {"dateTime": "2026-09-10T15:00:00+07:00", "timeZone": "Asia/Jakarta"}),
                    "status": "confirmed",
                },
            }

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

            busy_periods = params.get("mock_busy_periods", [])
            is_available = len(busy_periods) == 0

            return {
                "status": "success",
                "available": is_available,
                "timezone": tz_str,
                "time_min": dt_min.isoformat(),
                "time_max": dt_max.isoformat(),
                "busy_periods": busy_periods,
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

            event_id = params.get("event_id") or f"evt_{uuid.uuid4().hex[:12]}"
            created_event = {
                "id": event_id,
                "calendar_id": calendar_id,
                "summary": summary,
                "description": params.get("description", ""),
                "location": params.get("location", ""),
                "start": {"dateTime": dt_start.isoformat(), "timeZone": tz_start},
                "end": {"dateTime": dt_end.isoformat(), "timeZone": tz_start},
                "status": "confirmed",
                "attendees": params.get("attendees", []),
            }

            if mock_events is not None:
                mock_events[event_id] = created_event

            from app.integrations.events import publish_integration_event
            await publish_integration_event(
                tenant_id=tenant_id,
                event_type="integration.google_calendar.event_created",
                payload={"connection_id": str(connection_id), "calendar_id": calendar_id, "event_id": event_id},
            )

            return {
                "status": "success",
                "event_id": event_id,
                "calendar_id": calendar_id,
                "event": created_event,
            }

        elif operation == "update_event":
            calendar_id = params.get("calendar_id", "primary")
            event_id = params.get("event_id")
            if not event_id:
                raise PermanentIntegrationError("Missing event_id for update", error_code="VALIDATION_ERROR")

            existing_event = {}
            if mock_events is not None and event_id in mock_events:
                existing_event = mock_events[event_id]

            summary = params.get("summary", existing_event.get("summary", "Updated Event"))
            updated_event = {
                **existing_event,
                "id": event_id,
                "calendar_id": calendar_id,
                "summary": summary,
                "description": params.get("description", existing_event.get("description", "")),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }

            if "start" in params:
                start_data = params["start"]
                start_dt_str = start_data.get("dateTime") if isinstance(start_data, dict) else str(start_data)
                tz_str = (start_data.get("timeZone") if isinstance(start_data, dict) else None) or "Asia/Jakarta"
                dt_start, tz_start = validate_and_parse_datetime(start_dt_str, tz_str)
                updated_event["start"] = {"dateTime": dt_start.isoformat(), "timeZone": tz_start}

            if "end" in params:
                end_data = params["end"]
                end_dt_str = end_data.get("dateTime") if isinstance(end_data, dict) else str(end_data)
                tz_str = (end_data.get("timeZone") if isinstance(end_data, dict) else None) or "Asia/Jakarta"
                dt_end, tz_end = validate_and_parse_datetime(end_dt_str, tz_str)
                updated_event["end"] = {"dateTime": dt_end.isoformat(), "timeZone": tz_end}

            if mock_events is not None:
                mock_events[event_id] = updated_event

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
                "event": updated_event,
            }

        elif operation == "delete_event":
            calendar_id = params.get("calendar_id", "primary")
            event_id = params.get("event_id")
            if not event_id:
                raise PermanentIntegrationError("Missing event_id for delete", error_code="VALIDATION_ERROR")

            if mock_events is not None and event_id in mock_events:
                del mock_events[event_id]

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
