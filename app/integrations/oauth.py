import uuid
import hmac
import hashlib
import json
import time
import base64
from typing import Any
from app.core.config import settings
from app.integrations.exceptions import PermanentIntegrationError

# Default state validity duration: 15 minutes (900 seconds)
STATE_EXPIRATION_SECONDS = 900

# Cache/Set of used state nonces to prevent state replay attacks within lifetime
_USED_NONCES: dict[str, int] = {}


def _get_secret_key() -> bytes:
    key_str = settings.JWT_SECRET or settings.ENCRYPTION_KEY or "default_secure_oauth_secret_key_32_bytes_long"
    return key_str.encode("utf-8")


def generate_oauth_state(tenant_id: uuid.UUID, user_id: str | None = None, redirect_uri: str | None = None) -> str:
    """Generates an HMAC-signed, encrypted-like base64 OAuth state token bound to a tenant_id."""
    nonce = uuid.uuid4().hex
    now = int(time.time())
    expires_at = now + STATE_EXPIRATION_SECONDS

    state_payload = {
        "tenant_id": str(tenant_id),
        "user_id": user_id or "system",
        "redirect_uri": redirect_uri or "",
        "nonce": nonce,
        "created_at": now,
        "expires_at": expires_at,
    }

    payload_json = json.dumps(state_payload, sort_keys=True)
    payload_b64 = base64.urlsafe_b64encode(payload_json.encode("utf-8")).decode("utf-8")

    sig = hmac.new(_get_secret_key(), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()

    return f"{payload_b64}.{sig}"


def validate_oauth_state(state: str, expected_tenant_id: uuid.UUID) -> dict[str, Any]:
    """Validates an OAuth state token against CSRF, expiration, replay, and cross-tenant binding."""
    if not state or "." not in state:
        raise PermanentIntegrationError("Invalid OAuth state format", error_code="INVALID_STATE")

    parts = state.split(".", 1)
    payload_b64, sig = parts[0], parts[1]

    # Verify signature
    expected_sig = hmac.new(_get_secret_key(), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        raise PermanentIntegrationError("Tampered or invalid OAuth state signature", error_code="INVALID_STATE_SIGNATURE")

    # Decode payload
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64.encode("utf-8"))
        state_payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception as e:
        raise PermanentIntegrationError(f"Malformed OAuth state payload: {e}", error_code="MALFORMED_STATE")

    # Verify tenant binding
    state_tenant_id = state_payload.get("tenant_id")
    if not state_tenant_id or state_tenant_id != str(expected_tenant_id):
        raise PermanentIntegrationError("Cross-tenant OAuth state mismatch", error_code="CROSS_TENANT_STATE")

    # Verify expiration
    expires_at = state_payload.get("expires_at", 0)
    now = int(time.time())
    if now > expires_at:
        raise PermanentIntegrationError("OAuth state has expired", error_code="EXPIRED_STATE")

    # Cleanup expired nonces from memory cache
    expired_nonces = [n for n, exp in _USED_NONCES.items() if now > exp]
    for n in expired_nonces:
        del _USED_NONCES[n]

    # Verify anti-replay nonce
    nonce = state_payload.get("nonce")
    if not nonce or nonce in _USED_NONCES:
        raise PermanentIntegrationError("OAuth state has already been used or missing nonce", error_code="REUSED_STATE")

    _USED_NONCES[nonce] = expires_at

    return state_payload
