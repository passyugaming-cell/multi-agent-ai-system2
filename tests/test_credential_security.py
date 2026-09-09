import pytest
from app.integrations.credentials import redact_secrets


def test_redact_secrets_dict_keys():
    credentials = {
        "access_token": "ya29.a0AfH6SMB...",
        "refresh_token": "1//0e...",
        "api_key": "AIzaSyD...",
        "server_key": "SB-Mid-server-123456",
        "client_secret": "GOCSPX-abc123xyz",
        "app_secret": "meta_app_secret_999",
        "authorization": "Bearer eyJhbGciOi...",
        "verify_token": "my_webhook_verify_token",
        "nested": {
            "private_key": "-----BEGIN PRIVATE KEY-----...",
            "public_info": "safe_data_value",
        },
    }

    redacted = redact_secrets(credentials)

    assert redacted["access_token"] == "[REDACTED]"
    assert redacted["refresh_token"] == "[REDACTED]"
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["server_key"] == "[REDACTED]"
    assert redacted["client_secret"] == "[REDACTED]"
    assert redacted["app_secret"] == "[REDACTED]"
    assert redacted["authorization"] == "[REDACTED]"
    assert redacted["verify_token"] == "[REDACTED]"
    assert redacted["nested"]["private_key"] == "[REDACTED]"
    assert redacted["nested"]["public_info"] == "safe_data_value"


def test_redact_secrets_in_lists():
    item_list = [
        {"name": "conn_1", "access_token": "secret_val_1"},
        {"name": "conn_2", "server_key": "secret_val_2"},
        ["nested_list_item", {"bearer_token": "secret_val_3"}],
    ]

    redacted = redact_secrets(item_list)

    assert redacted[0]["access_token"] == "[REDACTED]"
    assert redacted[0]["name"] == "conn_1"
    assert redacted[1]["server_key"] == "[REDACTED]"
    assert redacted[2][1]["bearer_token"] == "[REDACTED]"


def test_redact_secrets_long_string_detection():
    long_secret = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6IkpvaG4gRG9lIiwiaWF0IjoxNTE2MjM5MDIyfQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
    normal_string = "Hello world from AI OS!"

    assert redact_secrets(long_secret) == "[REDACTED_SECRET]"
    assert redact_secrets(normal_string) == "Hello world from AI OS!"
