import uuid
import logging
import hashlib
import hmac
import secrets
import jwt
import redis.asyncio as aioredis
from datetime import datetime, timedelta, timezone
from typing import Optional, Any, Dict
from app.core.config import settings
from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

ALGORITHM = "HS256"
DEFAULT_EXPIRE_MINUTES = 60 * 24  # 24 hours


async def revoke_token_redis(jti: str, ttl_seconds: int = 86400) -> None:
    """Revoke a JWT token server-side by storing its JTI in Redis with TTL matching token expiration."""
    if not jti:
        return
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        await client.set(f"auth:revoked_jti:{jti}", "1", ex=ttl_seconds)
    except Exception as e:
        logger.error(f"Failed to revoke token in Redis for JTI {jti}: {e}")
        raise AppException(
            code="REVOCATION_STORAGE_FAILED",
            message="Failed to process session revocation securely",
            status_code=500,
        )
    finally:
        await client.aclose()


async def is_token_revoked_redis(jti: str) -> bool:
    """Check if a JWT token JTI is revoked in Redis. Fails closed on Redis errors."""
    if not jti:
        return True
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    try:
        val = await client.get(f"auth:revoked_jti:{jti}")
        return val is not None
    except Exception as e:
        logger.error(f"Redis error checking revocation for JTI {jti}: {e}")
        # Fail closed: reject authentication if revocation check fails
        raise AppException(
            code="REVOCATION_CHECK_FAILED",
            message="Security token status verification failed",
            status_code=401,
        )
    finally:
        await client.aclose()


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

    if "jti" not in to_encode:
        to_encode["jti"] = str(uuid.uuid4())

    to_encode.update({"exp": int(expire.timestamp())})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode and verify JWT signature and expiration claims (without async revocation check)."""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except Exception:
        return None


async def verify_and_decode_token(token: str) -> Optional[Dict[str, Any]]:
    """Decode JWT access token, verify signature, expiration, and check server-side Redis revocation status."""
    payload = decode_access_token(token)
    if not payload:
        return None

    jti = payload.get("jti")
    if jti:
        if await is_token_revoked_redis(jti):
            return None

    return payload
