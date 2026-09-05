from typing import Any


AGENT_PERMISSIONS: dict[str, dict[str, Any]] = {
    "owner_ai": {
        "allowed_tools": [
            "evaluate_business_health",
            "evaluate_client_health",
            "get_memory_context",
            "delegate_task_to_agent",
            "create_orchestration_task",
            "route_approval_request",
            "generate_daily_brief",
            "generate_weekly_review",
            "create_recommendation",
        ],
        "forbidden_actions": [
            "self_approve_high_risk",
            "change_security_policy",
            "change_platform_policy",
            "delete_critical_data",
            "change_official_price_unauthorized",
            "issue_refund_unauthorized",
            "direct_db_mutation",
        ],
        "read_only": False,
    },
    "ai_sales": {
        "allowed_tools": [
            "get_products",
            "get_pricing",
            "get_stock",
            "get_customer_conversation",
            "create_followup_task",
            "recommend_product",
            "recommend_discount",
        ],
        "forbidden_actions": [
            "change_official_price",
            "approve_discount",
            "issue_refund",
            "direct_db_mutation",
        ],
        "read_only": False,
    },
    "ai_client_manager": {
        "allowed_tools": [
            "get_client_onboarding_state",
            "calculate_readiness",
            "get_tenant_configuration",
            "create_onboarding_task",
            "list_onboarding_tasks",
            "recommend_configuration",
            "request_configuration_change",
        ],
        "forbidden_actions": [
            "change_critical_config",
            "bypass_approvals",
            "invent_client_data",
        ],
        "read_only": False,
    },
    "ai_support": {
        "allowed_tools": [
            "get_system_health",
            "get_whatsapp_status",
            "get_workflow_status",
            "get_integration_status",
            "get_task_status",
            "create_support_incident_task",
            "execute_low_risk_remediation",
        ],
        "forbidden_actions": [
            "critical_production_change",
            "claim_unverified_fix",
            "bypass_approvals",
        ],
        "read_only": False,
    },
    "ai_data_manager": {
        "allowed_tools": [
            "inspect_import_data",
            "validate_data_fields",
            "detect_data_conflicts",
            "detect_duplicates",
            "preview_import",
            "create_data_change_request",
        ],
        "forbidden_actions": [
            "invent_missing_data",
            "overwrite_trusted_data",
            "direct_unverified_import",
            "direct_db_update",
        ],
        "read_only": False,
    },
    "ai_analyst": {
        "allowed_tools": [
            "get_revenue_analytics",
            "get_sales_analytics",
            "get_customer_analytics",
            "get_order_analytics",
            "get_ai_usage_analytics",
            "get_support_analytics",
            "calculate_kpis",
            "generate_recommendation",
        ],
        "forbidden_actions": [
            "modify_business_data",
            "direct_db_mutation",
            "execute_transaction",
        ],
        "read_only": True,
    },
}


def check_tool_permission(agent_name: str, tool_name: str) -> bool:
    """Validate whether an agent has permission to invoke a specific tool."""
    agent_perms = AGENT_PERMISSIONS.get(agent_name)
    if not agent_perms:
        return False
    return tool_name in agent_perms.get("allowed_tools", [])
