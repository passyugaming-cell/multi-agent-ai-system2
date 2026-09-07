import uuid
from datetime import datetime, timezone
from typing import Any, List, Dict, Optional
from pydantic import BaseModel, Field


class ContextAssemblyRequest(BaseModel):
    """Input parameters requesting context assembly for AI execution."""

    tenant_id: uuid.UUID
    agent_name: Optional[str] = None
    task_type: Optional[str] = None
    query_text: Optional[str] = None
    customer_id: Optional[uuid.UUID] = None
    conversation_id: Optional[uuid.UUID] = None
    product_id: Optional[uuid.UUID] = None
    product_query: Optional[str] = None
    include_categories: Optional[List[str]] = None
    allow_internal: bool = False  # Bypasses client-header auth check for system-internal worker tasks


class AssembledContext(BaseModel):
    """Safe, minimum-necessary, structured AI context container.

    Enforces strict Source-of-Truth Hierarchy:
    1. System Truth (Database facts: price, stock, orders, status) - HIGHEST AUTHORITY
    2. Business Profile & Policies
    3. Approved Knowledge
    4. Conversation History
    5. Memory (Enrichment context - NEVER overrides system truth)
    """

    tenant_id: uuid.UUID
    agent_name: Optional[str] = None
    task_type: Optional[str] = None
    actor_id: Optional[str] = None
    actor_role: Optional[str] = None
    actor_permissions: List[str] = Field(default_factory=list)

    # 1. Real-time Database Facts (Price, stock, orders, status - SYSTEM TRUTH)
    facts: Dict[str, Any] = Field(default_factory=dict)

    # 2. Business Configuration & Profile
    business_profile: Optional[Dict[str, Any]] = None

    # 3. Approved Knowledge (Only APPROVED & ACTIVE knowledge)
    knowledge: List[Dict[str, Any]] = Field(default_factory=list)

    # 4. Customer Profile & Conversation Context
    customer: Optional[Dict[str, Any]] = None
    conversation_history: List[Dict[str, Any]] = Field(default_factory=list)

    # 5. Memory (Selective enrichment context)
    business_memory: List[Dict[str, Any]] = Field(default_factory=list)
    client_memory: List[Dict[str, Any]] = Field(default_factory=list)

    # 6. Task / Workflow State
    task_context: Optional[Dict[str, Any]] = None

    assembled_categories: List[str] = Field(default_factory=list)
    assembled_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class FormattedPromptContext(BaseModel):
    """Prompt-ready context formatted with boundary delimiters for prompt injection defense."""

    system_facts_block: str
    business_rules_block: str
    approved_knowledge_block: str
    business_memory_block: str
    client_memory_block: str
    conversation_history_block: str
    untrusted_user_input: str
    full_prompt: str
