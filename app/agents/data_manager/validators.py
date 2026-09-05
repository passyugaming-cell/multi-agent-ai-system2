from typing import Any


REQUIRED_PRODUCT_FIELDS = ["name", "price"]
REQUIRED_CUSTOMER_FIELDS = ["name", "phone"]


def validate_import_record(
    entity_type: str,
    record: dict[str, Any],
) -> tuple[bool, list[str], list[str]]:
    """Deterministically check for missing or invalid required fields in raw import data.

    Returns: (is_valid, missing_fields, invalid_fields)
    """
    missing_fields: list[str] = []
    invalid_fields: list[str] = []

    required_fields = (
        REQUIRED_PRODUCT_FIELDS if entity_type == "product"
        else REQUIRED_CUSTOMER_FIELDS if entity_type == "customer"
        else ["name"]
    )

    for field in required_fields:
        val = record.get(field)
        if val is None or str(val).strip() == "":
            missing_fields.append(field)

    if entity_type == "product" and "price" in record and "price" not in missing_fields:
        try:
            p_val = float(record["price"])
            if p_val < 0:
                invalid_fields.append("price (must be >= 0)")
        except (ValueError, TypeError):
            invalid_fields.append("price (must be a valid number)")

    is_valid = len(missing_fields) == 0 and len(invalid_fields) == 0
    return is_valid, missing_fields, invalid_fields
