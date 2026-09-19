import logging
from enum import Enum
from typing import Set, Optional, Any
from app.core.exceptions import AppException
from app.database.models.conversation import Conversation

logger = logging.getLogger(__name__)


class HumanHandoffState(str, Enum):
    RESUME_AI = "RESUME_AI"
    AI_HANDOFF_REQUESTED = "AI_HANDOFF_REQUESTED"
    HUMAN_ASSIGNED = "HUMAN_ASSIGNED"
    HUMAN_IN_PROGRESS = "HUMAN_IN_PROGRESS"
    RESOLVED = "RESOLVED"
    VERIFY = "VERIFY"
    CLOSE = "CLOSE"


ALLOWED_HANDOFF_TRANSITIONS: dict[HumanHandoffState, Set[HumanHandoffState]] = {
    HumanHandoffState.RESUME_AI: {
        HumanHandoffState.AI_HANDOFF_REQUESTED,
        HumanHandoffState.CLOSE,
    },
    HumanHandoffState.AI_HANDOFF_REQUESTED: {
        HumanHandoffState.HUMAN_ASSIGNED,
        HumanHandoffState.HUMAN_IN_PROGRESS,
        HumanHandoffState.RESUME_AI,
        HumanHandoffState.CLOSE,
    },
    HumanHandoffState.HUMAN_ASSIGNED: {
        HumanHandoffState.HUMAN_IN_PROGRESS,
        HumanHandoffState.RESOLVED,
        HumanHandoffState.RESUME_AI,
        HumanHandoffState.CLOSE,
    },
    HumanHandoffState.HUMAN_IN_PROGRESS: {
        HumanHandoffState.RESOLVED,
        HumanHandoffState.VERIFY,
        HumanHandoffState.RESUME_AI,
        HumanHandoffState.CLOSE,
    },
    HumanHandoffState.RESOLVED: {
        HumanHandoffState.VERIFY,
        HumanHandoffState.RESUME_AI,
        HumanHandoffState.CLOSE,
    },
    HumanHandoffState.VERIFY: {
        HumanHandoffState.RESUME_AI,
        HumanHandoffState.HUMAN_IN_PROGRESS,
        HumanHandoffState.CLOSE,
    },
    HumanHandoffState.CLOSE: {
        HumanHandoffState.RESUME_AI,
        HumanHandoffState.AI_HANDOFF_REQUESTED,
    },
}

# Deterministic mapping between HumanHandoffState and Conversation.status
HANDOFF_TO_CONVERSATION_STATUS_MAP: dict[HumanHandoffState, str] = {
    HumanHandoffState.AI_HANDOFF_REQUESTED: "WAITING_HUMAN",
    HumanHandoffState.HUMAN_ASSIGNED: "HUMAN_HANDLING",
    HumanHandoffState.HUMAN_IN_PROGRESS: "HUMAN_ACTIVE",
    HumanHandoffState.RESOLVED: "PENDING",
    HumanHandoffState.VERIFY: "PENDING",
    HumanHandoffState.RESUME_AI: "OPEN",
    HumanHandoffState.CLOSE: "CLOSED",
}


def validate_handoff_state_transition(current_state: str, target_state: str) -> None:
    """Enforces state transition validation for HumanHandoffState."""
    if current_state == target_state:
        return

    try:
        curr_enum = HumanHandoffState(current_state)
    except ValueError:
        curr_enum = None

    try:
        target_enum = HumanHandoffState(target_state)
    except ValueError:
        raise AppException(
            code="INVALID_HANDOFF_STATE_TRANSITION",
            message=f"Unknown target handoff state: '{target_state}'.",
            status_code=400,
        )

    if curr_enum:
        allowed = ALLOWED_HANDOFF_TRANSITIONS.get(curr_enum, set())
        if target_enum not in allowed:
            logger.warning(
                "Rejected invalid handoff state transition: '%s' -> '%s'",
                current_state,
                target_state,
            )
            raise AppException(
                code="INVALID_HANDOFF_STATE_TRANSITION",
                message=f"Cannot transition handoff state from '{current_state}' to '{target_state}'.",
                status_code=400,
            )


def get_handoff_lifecycle_state(conversation: Conversation) -> str:
    """Returns the authoritative HumanHandoffState from conversation metadata or derives it."""
    meta = conversation.metadata_ or {}
    if "handoff_state" in meta and meta["handoff_state"]:
        return meta["handoff_state"]

    # Derive default from Conversation.status if metadata is not yet populated
    c_status = conversation.status
    if c_status == "WAITING_HUMAN":
        return HumanHandoffState.AI_HANDOFF_REQUESTED.value
    elif c_status == "HUMAN_HANDLING":
        return HumanHandoffState.HUMAN_ASSIGNED.value
    elif c_status == "HUMAN_ACTIVE":
        return HumanHandoffState.HUMAN_IN_PROGRESS.value
    elif c_status == "PENDING":
        return HumanHandoffState.RESOLVED.value
    elif c_status == "CLOSED":
        return HumanHandoffState.CLOSE.value
    else:
        return HumanHandoffState.RESUME_AI.value


def sync_handoff_with_conversation_status(
    conversation: Conversation,
    target_handoff_state: str,
) -> str:
    """
    Validates handoff transition, sets conversation.metadata_['handoff_state'],
    and synchronizes Conversation.status deterministically.
    """
    current_handoff = get_handoff_lifecycle_state(conversation)
    validate_handoff_state_transition(current_handoff, target_handoff_state)

    target_enum = HumanHandoffState(target_handoff_state)
    meta = dict(conversation.metadata_ or {})
    meta["handoff_state"] = target_enum.value
    conversation.metadata_ = meta

    # Synchronize Conversation.status
    mapped_conv_status = HANDOFF_TO_CONVERSATION_STATUS_MAP.get(target_enum)
    if mapped_conv_status:
        conversation.status = mapped_conv_status

    return target_enum.value
