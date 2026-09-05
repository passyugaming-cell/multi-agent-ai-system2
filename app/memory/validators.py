import logging
from typing import Any
from app.memory.schemas import MemoryType, MemoryScope, MemoryCreateSchema, MemoryChangeProposalSchema
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


class MemoryValidator:
    """Enforces source-of-truth hierarchy, fact vs insight rules, and trust model boundaries."""

    @staticmethod
    def validate_memory_type_source(memory_type: MemoryType, source: str, confidence: float) -> tuple[MemoryType, float]:
        """Validate and coerce memory type based on source to prevent AI reasoning from becoming unverified FACT."""
        is_ai_source = source.startswith("ai") or "agent" in source.lower() or "gemini" in source.lower()

        # Rule: AI reasoning must NOT silently become permanent business FACT or POLICY
        if is_ai_source and memory_type == MemoryType.FACT:
            logger.info("Coercing AI-sourced memory from FACT to INSIGHT for source: %s", source)
            memory_type = MemoryType.INSIGHT
            # Bounded confidence for unverified AI insights
            confidence = min(confidence, 0.85)

        elif is_ai_source and memory_type == MemoryType.POLICY:
            logger.info("Coercing AI-sourced memory from POLICY to INSIGHT for source: %s", source)
            memory_type = MemoryType.INSIGHT
            confidence = min(confidence, 0.80)

        # Confidence bounds validation
        confidence = max(0.0, min(1.0, round(confidence, 4)))
        return memory_type, confidence

    @staticmethod
    def requires_approval_for_change(scope: MemoryScope, key: str, memory_type: MemoryType, source: str) -> bool:
        """Determines if a memory change requires explicit Human Owner approval proposal."""
        # Critical policy changes or owner decisions from AI agents require approval
        if memory_type in (MemoryType.POLICY, MemoryType.DECISION, MemoryType.CONSTRAINT):
            if source.startswith("ai") or "agent" in source.lower():
                return True
        return False
