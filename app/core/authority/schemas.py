import hashlib
import json
import uuid
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

from app.core.context import AuthenticatedActor


class ActionRiskLevel(str, Enum):
    """Deterministic action risk levels across AI Business OS."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ExecutionDecision(str, Enum):
    """Centralized action evaluation decision."""
    ALLOW = "ALLOW"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    DENY = "DENY"


class ActionBinding(BaseModel):
    """Deterministic binding representation for action parameters and target context."""
    model_config = ConfigDict(frozen=True)

    action_type: str
    target: str
    tenant_id: str
    params_hash: str

    @classmethod
    def compute_hash(
        cls,
        action_type: str,
        target: str,
        tenant_id: str | uuid.UUID,
        params: Optional[dict[str, Any]] = None,
    ) -> str:
        """Computes a deterministic SHA256 hex digest binding an action request."""
        clean_params = params or {}
        # Filter internal ephemeral metadata keys starting with '_' before hashing
        serializable_params = {
            k: v for k, v in clean_params.items() if not k.startswith("_")
        }
        raw_payload = {
            "action_type": str(action_type).strip().lower(),
            "target": str(target).strip().lower(),
            "tenant_id": str(tenant_id).strip().lower(),
            "params": serializable_params,
        }
        encoded = json.dumps(raw_payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class ActionRequest(BaseModel):
    """Standardized request payload evaluated by ActionAuthorizationService."""
    model_config = ConfigDict(arbitrary_types_allowed=True)

    action_type: str
    target: str
    tenant_id: uuid.UUID
    actor: Optional[AuthenticatedActor] = None
    agent_id: Optional[str] = None
    params: dict[str, Any] = Field(default_factory=dict)
    approval_id: Optional[uuid.UUID] = None
    correlation_id: Optional[str] = None

    def compute_action_hash(self) -> str:
        """Helper computing deterministic binding hash for this action request."""
        return ActionBinding.compute_hash(
            action_type=self.action_type,
            target=self.target,
            tenant_id=self.tenant_id,
            params=self.params,
        )


class AuthorizationDecision(BaseModel):
    """Structured decision output produced by ActionAuthorizationService."""
    decision: ExecutionDecision
    risk_level: ActionRiskLevel
    reason: str
    approval_id: Optional[uuid.UUID] = None
    action_hash: Optional[str] = None
    required_permissions: set[str] = Field(default_factory=set)
