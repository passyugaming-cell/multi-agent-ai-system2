from typing import Any

OWNER_AI_ALLOWED_TOOLS = [
    "evaluate_business_health",
    "evaluate_client_health",
    "get_memory_context",
    "delegate_task_to_agent",
    "create_orchestration_task",
    "route_approval_request",
    "generate_daily_brief",
    "generate_weekly_review",
    "create_recommendation",
]

OWNER_AI_FORBIDDEN_ACTIONS = [
    "self_approve_high_risk",
    "change_security_policy",
    "change_platform_policy",
    "delete_critical_data",
    "change_official_price_unauthorized",
    "issue_refund_unauthorized",
    "direct_db_mutation",
]

# Runaway orchestration safeguards
MAX_AGENTS_PER_ORCHESTRATION = 5
MAX_AGENT_CALLS_PER_RUN = 10
MAX_DELEGATION_DEPTH = 3
ORCHESTRATION_TIMEOUT_SECONDS = 60
