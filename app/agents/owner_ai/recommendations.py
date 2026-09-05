import uuid
from datetime import datetime, timezone
from typing import Sequence
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.owner_ai import Recommendation
from app.agents.owner_ai.schemas import RecommendationSchema, RecommendationStatus, RecommendationPriority
from app.core.exceptions import AppError


class RecommendationService:
    """Service layer managing Owner AI recommendations and the auditable feedback loop."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session

    async def create_recommendation(
        self,
        tenant_id: uuid.UUID,
        title: str,
        problem: str,
        reasoning_summary: str,
        expected_benefit: str,
        suggested_action: str,
        evidence: list | None = None,
        risk: str = "LOW",
        confidence: float = 1.0,
        required_approval: bool = False,
        approval_id: uuid.UUID | None = None,
        priority: str = "NORMAL",
        execution_id: uuid.UUID | None = None,
    ) -> RecommendationSchema:
        if evidence is None:
            evidence = []

        rec = Recommendation(
            tenant_id=tenant_id,
            execution_id=execution_id,
            title=title,
            problem=problem,
            evidence=evidence,
            reasoning_summary=reasoning_summary,
            expected_benefit=expected_benefit,
            risk=risk,
            confidence=max(0.0, min(1.0, round(confidence, 4))),
            suggested_action=suggested_action,
            required_approval=required_approval,
            approval_id=approval_id,
            priority=priority,
            status="PROPOSED",
        )
        self.session.add(rec)
        await self.session.commit()
        await self.session.refresh(rec)

        return RecommendationSchema(
            recommendation_id=rec.id,
            tenant_id=rec.tenant_id,
            title=rec.title,
            problem=rec.problem,
            evidence=rec.evidence,
            reasoning_summary=rec.reasoning_summary,
            expected_benefit=rec.expected_benefit,
            risk=rec.risk,
            confidence=rec.confidence,
            suggested_action=rec.suggested_action,
            required_approval=rec.required_approval,
            approval_id=rec.approval_id,
            priority=RecommendationPriority(rec.priority),
            status=RecommendationStatus(rec.status),
            created_at=rec.created_at,
        )

    async def list_recommendations(
        self,
        tenant_id: uuid.UUID,
        status: str | None = None,
    ) -> list[RecommendationSchema]:
        filters = [Recommendation.tenant_id == tenant_id]
        if status:
            filters.append(Recommendation.status == status)

        stmt = select(Recommendation).where(and_(*filters)).order_by(Recommendation.created_at.desc())
        recs = (await self.session.execute(stmt)).scalars().all()

        return [
            RecommendationSchema(
                recommendation_id=r.id,
                tenant_id=r.tenant_id,
                title=r.title,
                problem=r.problem,
                evidence=r.evidence,
                reasoning_summary=r.reasoning_summary,
                expected_benefit=r.expected_benefit,
                risk=r.risk,
                confidence=r.confidence,
                suggested_action=r.suggested_action,
                required_approval=r.required_approval,
                approval_id=r.approval_id,
                priority=RecommendationPriority(r.priority),
                status=RecommendationStatus(r.status),
                created_at=r.created_at,
            )
            for r in recs
        ]

    async def update_status(
        self,
        tenant_id: uuid.UUID,
        recommendation_id: uuid.UUID,
        new_status: RecommendationStatus,
    ) -> RecommendationSchema:
        stmt = select(Recommendation).where(
            and_(Recommendation.id == recommendation_id, Recommendation.tenant_id == tenant_id)
        )
        rec = (await self.session.execute(stmt)).scalar_one_or_none()
        if not rec:
            raise AppError("Recommendation not found.", status_code=404)

        rec.status = new_status.value
        await self.session.commit()
        await self.session.refresh(rec)

        return RecommendationSchema(
            recommendation_id=rec.id,
            tenant_id=rec.tenant_id,
            title=rec.title,
            problem=rec.problem,
            evidence=rec.evidence,
            reasoning_summary=rec.reasoning_summary,
            expected_benefit=rec.expected_benefit,
            risk=rec.risk,
            confidence=rec.confidence,
            suggested_action=rec.suggested_action,
            required_approval=rec.required_approval,
            approval_id=rec.approval_id,
            priority=RecommendationPriority(rec.priority),
            status=RecommendationStatus(rec.status),
            created_at=rec.created_at,
        )
