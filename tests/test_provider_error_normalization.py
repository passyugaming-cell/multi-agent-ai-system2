import pytest
from app.integrations.credentials import redact_secrets


def test_redact_secrets_sanitizes_provider_error_payloads():
    raw_error_payload = {
        "provider": "google_calendar",
        "error": {
            "code": 401,
            "message": "Invalid credentials provided",
            "details": [
                {"access_token": "ya29.secret_token_value_12345", "client_secret": "GOCSPX-secret_secret_67890"}
            ],
        },
    }

    sanitized = redact_secrets(raw_error_payload)

    assert sanitized["error"]["details"][0]["access_token"] == "[REDACTED]"
    assert sanitized["error"]["details"][0]["client_secret"] == "[REDACTED]"
    assert sanitized["error"]["message"] == "Invalid credentials provided"
