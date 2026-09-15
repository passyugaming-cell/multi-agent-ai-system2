class InvalidStateTransitionError(Exception):
    """Raised when an illegal or unsupported state machine transition is attempted."""

    def __init__(self, current_status: str, target_status: str):
        self.current_status = current_status
        self.target_status = target_status
        super().__init__(f"Invalid message status transition: cannot transition from '{current_status}' to '{target_status}'.")


VALID_MESSAGE_TRANSITIONS: dict[str, set[str]] = {
    "CREATED": {"QUEUED", "FAILED", "UNKNOWN"},
    "QUEUED": {"SENDING", "FAILED", "UNKNOWN"},
    "SENDING": {"SENT", "FAILED", "UNKNOWN"},
    "SENT": {"DELIVERED", "FAILED", "UNKNOWN"},
    "DELIVERED": {"READ", "FAILED", "UNKNOWN"},
    "READ": set(),      # Terminal status
    "FAILED": set(),    # Terminal status
    "UNKNOWN": set(),   # Terminal status without explicit reconciliation
}


def validate_message_status_transition(current_status: str, target_status: str) -> None:
    """Enforces state transition rules for Message entities."""
    if current_status == target_status:
        return

    allowed = VALID_MESSAGE_TRANSITIONS.get(current_status, set())
    if target_status not in allowed:
        raise InvalidStateTransitionError(current_status, target_status)
