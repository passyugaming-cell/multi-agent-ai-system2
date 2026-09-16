import re
from app.core.exceptions import AppException


class PhoneNormalizationError(AppException):
    """Raised when phone number cannot be normalized safely."""

    def __init__(self, message: str, phone_raw: str | None = None):
        super().__init__(
            code="INVALID_PHONE_FORMAT",
            message=message,
            status_code=400,
            details={"phone_raw": phone_raw} if phone_raw else {},
        )


def normalize_phone_number(phone: str | None, default_country_code: str = "62") -> str:
    """
    Canonical phone normalization for WhatsApp messaging.
    Enforces standard digits-only format with country prefix (e.g. '628123456789').

    Behavior:
    - Strips spaces, hyphens, plus signs, brackets, and non-digit characters.
    - Handles '08xxxxxxxx' -> '628xxxxxxxx' (if default_country_code == '62').
    - Handles '+628xxxxxxx' or '628xxxxxxx' -> '628xxxxxxx'.
    - Validates digit length (minimum 8, maximum 15 digits as per E.164 standard).
    - Fails closed on empty, whitespace, or invalid non-numeric format.
    """
    if not phone or not isinstance(phone, str):
        raise PhoneNormalizationError("Phone number must be a non-empty string.", phone_raw=str(phone))

    raw = phone.strip()
    if not raw:
        raise PhoneNormalizationError("Phone number cannot be empty or blank.", phone_raw=phone)

    # Strip standard formatting symbols
    cleaned = re.sub(r"[\s\-\+\(\)]", "", raw)

    # Reject if any non-digits remain
    if not cleaned.isdigit():
        raise PhoneNormalizationError(
            f"Phone number '{phone}' contains invalid non-numeric characters.",
            phone_raw=phone,
        )

    # Local ID prefix conversion: 08... -> 628...
    if cleaned.startswith("0"):
        if len(cleaned) < 9:
            raise PhoneNormalizationError(
                f"Local phone number '{phone}' is too short.",
                phone_raw=phone,
            )
        cleaned = default_country_code + cleaned[1:]

    # Length check according to E.164 (max 15 digits)
    if len(cleaned) < 8 or len(cleaned) > 15:
        raise PhoneNormalizationError(
            f"Normalized phone number '{cleaned}' length is invalid (must be 8-15 digits).",
            phone_raw=phone,
        )

    return cleaned
