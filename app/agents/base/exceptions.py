class AgentError(Exception):
    """Base exception for agent layer."""
    pass


class AgentExecutionError(AgentError):
    """Raised when agent execution fails."""
    pass


class AgentValidationError(AgentError):
    """Raised when agent input/output schema validation fails."""
    pass


class AgentPermissionError(AgentError):
    """Raised when agent exceeds capability boundaries or tool permissions."""
    pass


class AgentRecursionError(AgentError):
    """Raised when maximum agent delegation depth is exceeded."""
    pass


class ToolExecutionError(AgentError):
    """Raised when a tool fails to execute or violates safety rules."""
    pass
