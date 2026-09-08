import uuid
import hashlib
import hmac
import secrets
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict, Set
from app.core.config import settings

ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 60 * 24  # 24 hours

# Server-side in-memory revoked token identifiers (JTIs)
_revoked_jtis: Set[str] = set()


def revoke_token(jti: str) -> None:
    """Revoke a JWT token by adding its unique identifier (jti) to the revoked set."""
    if jti:
        _revoked_jtis.add(jti)


def is_token_revoked(jti: str) -> bool:
    """Check if a JWT token has been revoked server-side."""
    return jti in _revoked_jtis


def hash_password(password: str) -> str:
    """Hash password using PBKDF2-HMAC-SHA256 with random salt."""
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return f"pbkdf2:sha256:100000${salt.hex()}${dk.hex()}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against hashed password string in constant time."""
    try:
        if not hashed_password or "$" not in hashed_password:
            return False
        parts = hashed_password.split("$")
        if len(parts) != 3 or not parts[0].startswith("pbkdf2:sha256"):
            return False
        iterations = int(parts[0].split(":")[2])
        salt = bytes.fromhex(parts[1])
        expected_dk = bytes.fromhex(parts[2])

        dk = hashlib.pbkdf2_hmac("sha256", plain_password.encode("utf-8"), salt, iterations)
        return hmac.compare_digest(dk, expected_dk)
    except Exception:
        return False


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create a signed JWT access token containing subject claims and unique JTI."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=DEFAULT_EXPIRE_MINUTES)

    # Ensure JTI exists
    if "jti" not in to_encode:
        to_encode["jti"] = str(uuid.uuid4())

    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode, verify signature and expiration, and check revocation status of JWT access token."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti and is_token_revoked(jti):
            return None
        return payload
    except Exception:
        return None
