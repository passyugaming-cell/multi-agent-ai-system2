from typing import Any
import uuid
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.schemas import ToolRequest, ToolResult
from app.agents.data_manager.validators import validate_import_record
from app.database.models.product import Product
from app.database.models.customer import Customer


async def inspect_import_data_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Parse and inspect raw import data without modifying any DB record."""
    raw_records = tool_req.parameters.get("records", [])
    entity_type = tool_req.parameters.get("entity_type", "product")

    parsed_summary = {
        "record_count": len(raw_records),
        "entity_type": entity_type,
        "sample_record": raw_records[0] if raw_records else None,
    }

    return ToolResult(
        success=True,
        tool_name="inspect_import_data",
        data=parsed_summary,
        evidence=[{"inspected_records": len(raw_records)}],
        metadata={"tenant_id": str(tool_req.tenant_id)},
        correlation_id=tool_req.correlation_id,
    )


async def validate_data_fields_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Deterministically validate records for missing or invalid fields."""
    raw_records = tool_req.parameters.get("records", [])
    entity_type = tool_req.parameters.get("entity_type", "product")

    all_missing = []
    all_invalid = []
    valid_count = 0

    for idx, rec in enumerate(raw_records):
        is_valid, missing, invalid = validate_import_record(entity_type, rec)
        if is_valid:
            valid_count += 1
        else:
            if missing:
                all_missing.append({"record_index": idx, "missing_fields": missing, "record": rec})
            if invalid:
                all_invalid.append({"record_index": idx, "invalid_fields": invalid, "record": rec})

    overall_valid = len(all_missing) == 0 and len(all_invalid) == 0

    return ToolResult(
        success=True,
        tool_name="validate_data_fields",
        data={
            "overall_valid": overall_valid,
            "total_records": len(raw_records),
            "valid_records_count": valid_count,
            "missing_field_records": all_missing,
            "invalid_field_records": all_invalid,
        },
        evidence=[{"overall_valid": overall_valid, "missing_count": len(all_missing)}],
        metadata={"tenant_id": str(tool_req.tenant_id)},
        correlation_id=tool_req.correlation_id,
    )


async def detect_data_conflicts_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Check for existing duplicate records in database."""
    raw_records = tool_req.parameters.get("records", [])
    entity_type = tool_req.parameters.get("entity_type", "product")

    conflicts = []

    if entity_type == "product":
        for rec in raw_records:
            name = rec.get("name")
            if name:
                stmt = select(Product).where(
                    and_(Product.tenant_id == tool_req.tenant_id, Product.name.ilike(name))
                )
                existing = (await session.execute(stmt)).scalar_one_or_none()
                if existing:
                    conflicts.append({
                        "entity": "product",
                        "name": name,
                        "existing_id": str(existing.id),
                        "existing_price": float(existing.price),
                    })

    return ToolResult(
        success=True,
        tool_name="detect_data_conflicts",
        data={"conflicts_detected": conflicts, "conflict_count": len(conflicts)},
        evidence=[{"conflict_count": len(conflicts)}],
        metadata={"tenant_id": str(tool_req.tenant_id)},
        correlation_id=tool_req.correlation_id,
    )


async def create_data_change_request_tool(tool_req: ToolRequest, session: AsyncSession) -> ToolResult:
    """Generate a formal data change request requiring human approval."""
    change_type = tool_req.parameters.get("change_type", "bulk_import")
    summary = tool_req.parameters.get("summary", "")

    return ToolResult(
        success=True,
        tool_name="create_data_change_request",
        data={
            "change_type": change_type,
            "summary": summary,
            "requires_approval": True,
        },
        evidence=[{"change_type": change_type}],
        metadata={"requires_approval": True},
        correlation_id=tool_req.correlation_id,
    )
