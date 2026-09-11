from typing import Any, Optional
from app.core.authority.schemas import ActionRiskLevel


# Deterministic action risk mapping
ACTION_RISK_POLICY_MAP: dict[str, ActionRiskLevel] = {
    # LOW Risk - Read-only, logging, tags, internal messages
    "send_message": ActionRiskLevel.LOW,
    "create_task": ActionRiskLevel.LOW,
    "add_tag": ActionRiskLevel.LOW,
    "remove_tag": ActionRiskLevel.LOW,
    "log_result": ActionRiskLevel.LOW,
    "delay": ActionRiskLevel.LOW,
    "emit_event": ActionRiskLevel.LOW,
    "midtrans_check_status": ActionRiskLevel.LOW,
    "get_business_profile": ActionRiskLevel.LOW,
    "read_catalog": ActionRiskLevel.LOW,

    # MEDIUM Risk - Non-destructive standard entity updates, integrations, standard agent execution
    "update_customer": ActionRiskLevel.MEDIUM,
    "update_order": ActionRiskLevel.MEDIUM,
    "call_ai": ActionRiskLevel.MEDIUM,
    "call_agent": ActionRiskLevel.MEDIUM,
    "owner_ai": ActionRiskLevel.MEDIUM,
    "run_owner_ai": ActionRiskLevel.MEDIUM,
    "call_owner_ai": ActionRiskLevel.MEDIUM,
    "google_calendar_create_event": ActionRiskLevel.MEDIUM,
    "google_sheets_append": ActionRiskLevel.MEDIUM,
    "google_sheets_update": ActionRiskLevel.MEDIUM,
    "whatsapp_send_message": ActionRiskLevel.MEDIUM,
    "midtrans_create_payment": ActionRiskLevel.MEDIUM,
    "execute_integration": ActionRiskLevel.MEDIUM,

    # HIGH Risk - Financial operations, cancellation, pricing changes, workflow route approval
    "midtrans_cancel_payment": ActionRiskLevel.HIGH,
    "midtrans_request_refund": ActionRiskLevel.HIGH,
    "change_product_price": ActionRiskLevel.HIGH,
    "change_official_price": ActionRiskLevel.HIGH,
    "issue_refund": ActionRiskLevel.HIGH,
    "request_approval": ActionRiskLevel.HIGH,
    "route_approval_request": ActionRiskLevel.HIGH,
    "create_orchestration_task": ActionRiskLevel.HIGH,

    # CRITICAL Risk - Data deletion, security policy modifications, tenant lifecycle alteration
    "delete_customer": ActionRiskLevel.CRITICAL,
    "delete_data": ActionRiskLevel.CRITICAL,
    "delete_critical_data": ActionRiskLevel.CRITICAL,
    "change_critical_config": ActionRiskLevel.CRITICAL,
    "modify_security_policy": ActionRiskLevel.CRITICAL,
    "activate_tenant": ActionRiskLevel.CRITICAL,
    "deactivate_tenant": ActionRiskLevel.CRITICAL,
}

# Deterministic required permission mapping for MEDIUM-risk actions
ACTION_PERMISSION_MAP: dict[str, str] = {
    "update_customer": "business.write",
    "update_order": "business.write",
    "call_ai": "business.read",
    "call_agent": "business.read",
    "owner_ai": "business.read",
    "run_owner_ai": "business.read",
    "call_owner_ai": "business.read",
    "google_calendar_create_event": "EXECUTE_INTEGRATION",
    "google_sheets_append": "EXECUTE_INTEGRATION",
    "google_sheets_update": "EXECUTE_INTEGRATION",
    "whatsapp_send_message": "SEND_WHATSAPP_MESSAGE",
    "midtrans_create_payment": "MANAGE_PAYMENTS",
    "execute_integration": "EXECUTE_INTEGRATION",
}


def get_required_action_permission(action_type: str) -> str:
    """Returns the required permission string for a given action."""
    clean_action = str(action_type).strip().lower()
    return ACTION_PERMISSION_MAP.get(clean_action, "business.read")


class RiskClassifier:
    """Deterministic Risk Classifier for AI Business OS actions."""

    @classmethod
    def classify(
        cls,
        action_type: str,
        params: Optional[dict[str, Any]] = None,
    ) -> ActionRiskLevel:
        """Classifies an action request into a deterministic ActionRiskLevel."""
        clean_action = str(action_type).strip().lower()

        # Check explicit policy mapping
        if clean_action in ACTION_RISK_POLICY_MAP:
            return ACTION_RISK_POLICY_MAP[clean_action]

        # Parameter-based override checks for standard keys
        params_dict = params or {}
        if params_dict.get("is_critical") is True or params_dict.get("scope") == "critical":
            return ActionRiskLevel.CRITICAL

        if params_dict.get("is_high_risk") is True or params_dict.get("financial_impact") == "high":
            return ActionRiskLevel.HIGH

        # Default fallback for unknown actions: fail-safe HIGH risk
        return ActionRiskLevel.HIGH
