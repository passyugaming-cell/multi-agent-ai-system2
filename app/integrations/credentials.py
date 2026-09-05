import base64
import json
import logging
import re
from typing import Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from app.core.config import settings
from app.integrations.exceptions import CredentialSecurityError

logger = logging.getLogger(__name__)

SECRET_KEY_PATTERNS = re.compile(
    r"(secret|password|token|api_key|apikey|private|credential|authorization|bearer|auth|access_token|refresh_token)",
    re.IGNORECASE,
)


def _get_fernet_key() -> bytes:
    """Derive a deterministic 32-byte url-safe Fernet key from settings.ENCRYPTION_KEY."""
    raw_key = getattr(settings, "ENCRYPTION_KEY", None) or "default_phase6_integration_key_32_bytes_long"
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"ai_os_integration_salt",
        iterations=100000,
    )
    derived = kdf.derive(raw_key.encode())
    return base64.urlsafe_b64encode(derived)


class CredentialVault:
    """Provides secure encryption, decryption, and redaction for integration secrets."""

    def __init__(self) -> None:
        try:
            fernet_key = _get_fernet_key()
            self._fernet = Fernet(fernet_key)
        except Exception as e:
            logger.error("Failed to initialize CredentialVault Fernet instance: %s", e)
            raise CredentialSecurityError("Failed to initialize credential encryption engine") from e

    def encrypt_credentials(self, credentials_dict: dict[str, Any]) -> str:
        """Serializes credentials to JSON and encrypts with Fernet."""
        try:
            json_data = json.dumps(credentials_dict).encode("utf-8")
            encrypted_bytes = self._fernet.encrypt(json_data)
            return encrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error("Credential encryption failed: %s", e)
            raise CredentialSecurityError("Failed to encrypt credentials") from e

    def decrypt_credentials(self, encrypted_secret: str) -> dict[str, Any]:
        """Decrypts Fernet ciphertext and deserializes JSON to dict."""
        try:
            decrypted_bytes = self._fernet.decrypt(encrypted_secret.encode("utf-8"))
            return json.loads(decrypted_bytes.decode("utf-8"))
        except Exception as e:
            logger.error("Credential decryption failed: %s", e)
            raise CredentialSecurityError("Failed to decrypt credentials or invalid ciphertext") from e


def redact_secrets(data: Any) -> Any:
    """Recursively redacts sensitive keys/values from dictionaries, lists, and structures."""
    if isinstance(data, dict):
        redacted = {}
        for key, value in data.items():
            if SECRET_KEY_PATTERNS.search(str(key)):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_secrets(value)
        return redacted
    elif isinstance(data, list):
        return [redact_secrets(item) for item in data]
    elif isinstance(data, str):
        if SECRET_KEY_PATTERNS.search(data) and len(data) > 20:
            return "[REDACTED_SECRET]"
        return data
    return data
