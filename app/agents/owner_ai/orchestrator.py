import uuid
from datetime import datetime, timezone
import logging
from typing import Any, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.owner_ai import OwnerAIExecution
from app.agents.base.schemas import AgentRequest, AgentResult, AgentRequestStatus
from app.agents.base.registry import agent_registry
from app.agents.owner_ai.health import BusinessHealthCalculator, ClientHealthCalculator
from app.agents.owner_ai.recommendations import RecommendationService
from app.agents.owner_ai.approvals import ApprovalRouter
from app.agents.owner_ai.schemas import RecommendationSchema, RecommendationPriority, RecommendationStatus
from app.agents.owner_ai.policies import (
    MAX_AGENTS_PER_ORCHESTRATION,
    MAX_AGENT_CALLS_PER_RUN,
    MAX_DELEGATION_DEPTH,
)
from app.memory.service import MemoryService
from app.core.tasks.service import TaskService
from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


class OwnerAIOrchestrator:
    """Central multi-agent orchestrator managing task distribution, execution state, runaway limits, and result consolidation."""

    def __init__(self, db_session: AsyncSession) -> None:
        self.session = db_session
        self.task_service = TaskService(db_session)
        self.rec_service = RecommendationService(db_session)
        self.mem_service = MemoryService(db_session)
        self.approval_router = ApprovalRouter(db_session)

    async def orchestrate(
        self,
        tenant_id: uuid.UUID,
        objective: str,
        context: dict | None = None,
        correlation_id: str | None = None,
        delegation_depth: int = 0,
    ) -> AgentResult:
        if context is None:
            context = {}

        # Protection against runaway orchestration depth
        if delegation_depth >= MAX_DELEGATION_DEPTH:
            return AgentResult(
                request_id=f"req_{uuid.uuid4().hex[:12]}",
                agent="owner_ai",
                status=AgentRequestStatus.BLOCKED,
                error=f"Orchestration delegation depth limit exceeded ({delegation_depth} >= {MAX_DELEGATION_DEPTH})",
                correlation_id=correlation_id,
            )

        # 1. Create persistent execution record
        exec_record = OwnerAIExecution(
            tenant_id=tenant_id,
            objective=objective,
            status="CREATED",
            started_at=datetime.now(timezone.utc),
            agents_called=[],
            tasks_created=[],
            events_used=[],
            recommendations=[],
            approvals=[],
            correlation_id=correlation_id,
        )
        self.session.add(exec_record)
        await self.session.commit()
        await self.session.refresh(exec_record)

        agents_called: List[str] = []
        tasks_created: List[Dict[str, Any]] = []
        collected_results: List[AgentResult] = []
        evidence_list: List[Any] = []
        recommendations_created: List[RecommendationSchema] = []
        needs_approval = False
        approval_id = None
        has_partial_failure = False

        try:
            # 2. State: PLANNING
            exec_record.status = "PLANNING"
            await self.session.commit()

            # Retrieve business health and assemble structured owner context
            health = await BusinessHealthCalculator.calculate(self.session, tenant_id)

            from app.core.context_assembly import ContextAssemblyService, ContextAssemblyRequest

            assembly_service = ContextAssemblyService(self.session)
            assembled_ctx = await assembly_service.assemble_context(
                ContextAssemblyRequest(
                    tenant_id=tenant_id,
                    agent_name="owner_ai",
                    task_type="orchestration",
                    query_text=objective,
                )
            )

            evidence_list.append(f"Business Health Score: {health.score}/100")
            for m in assembled_ctx.business_memory:
                evidence_list.append(f"Business Memory [{m.get('key')}]: {m.get('content')}")

            # Determine relevant agents based on objective
            obj_lower = objective.lower()
            target_agents = []
            if "sale" in obj_lower or "conversion" in obj_lower or "revenue" in obj_lower or "business" in obj_lower:
                target_agents.extend(["ai_analyst", "ai_sales", "ai_client_manager", "ai_support"])
            elif "client" in obj_lower or "onboarding" in obj_lower:
                target_agents.extend(["ai_client_manager", "ai_support"])
            elif "support" in obj_lower or "incident" in obj_lower or "health" in obj_lower:
                target_agents.extend(["ai_support", "ai_analyst"])
            else:
                target_agents.extend(["ai_analyst", "ai_sales", "ai_client_manager"])

            # Deduplicate and enforce max agents limit
            target_agents = list(dict.fromkeys(target_agents))[:MAX_AGENTS_PER_ORCHESTRATION]

            # 3. State: DELEGATING & WAITING_FOR_AGENTS
            exec_record.status = "DELEGATING"
            await self.session.commit()

            for target_agent in target_agents:
                if len(agents_called) >= MAX_AGENT_CALLS_PER_RUN:
                    logger.warning("Reached max agent calls limit per run (%d)", MAX_AGENT_CALLS_PER_RUN)
                    break

                # Create task in Task System
                task = await self.task_service.create_task(
                    tenant_id=tenant_id,
                    title=f"Analyze for objective: {objective[:50]}...",
                    description=objective,
                    task_type=f"analysis_{target_agent}",
                    priority="NORMAL",
                    assigned_agent=target_agent,
                    source="owner_ai",
                )
                tasks_created.append({"task_id": str(task.id), "agent": target_agent, "status": task.status})

                # Dispatch AgentRequest via AgentRegistry
                req = AgentRequest(
                    tenant_id=tenant_id,
                    source="owner_ai",
                    source_agent="owner_ai",
                    target_agent=target_agent,
                    task_type="analyze_objective",
                    objective=objective,
                    context={"task_id": str(task.id), "health_score": health.score, "objective": objective},
                    correlation_id=correlation_id,
                    delegation_depth=delegation_depth + 1,
                )

                agents_called.append(target_agent)

                try:
                    res = await agent_registry.delegate_task(req, self.session)
                    collected_results.append(res)

                    # Update task status
                    if res.status == AgentRequestStatus.COMPLETED:
                        await self.task_service.update_status(
                            tenant_id, task.id, "COMPLETED", result={"finding": res.finding}
                        )
                    elif res.status in (AgentRequestStatus.FAILED, AgentRequestStatus.BLOCKED):
                        has_partial_failure = True
                        await self.task_service.update_status(
                            tenant_id, task.id, "FAILED", error=res.error
                        )
                    elif res.status == AgentRequestStatus.WAITING_APPROVAL:
                        needs_approval = True
                        approval_id = res.approval_id
                        await self.task_service.update_status(
                            tenant_id, task.id, "WAITING_APPROVAL"
                        )

                    if res.finding:
                        evidence_list.append(f"{target_agent}: {res.finding}")
                    if res.evidence:
                        evidence_list.extend(res.evidence)

                except Exception as agent_exc:
                    logger.error("Error delegating task to agent %s: %s", target_agent, agent_exc)
                    has_partial_failure = True
                    await self.task_service.update_status(
                        tenant_id, task.id, "FAILED", error=str(agent_exc)
                    )

            # 4. State: ANALYZING
            exec_record.status = "ANALYZING"
            await self.session.commit()

            # Consolidate findings
            consolidated_facts = [
                f"Business Health Score is {health.score}/100 with category breakdown: {health.category_scores}.",
                f"Historical 30-day revenue: ${health.historical_comparison.get('curr_30d_revenue', 0.0):,.2f}.",
            ]
            consolidated_causes = []
            for r in collected_results:
                if r.status == AgentRequestStatus.COMPLETED and r.finding:
                    consolidated_causes.append(f"[{r.agent}]: {r.finding}")

            findings_summary = (
                f"Multi-agent investigation completed with {len(collected_results)} agents called. "
                + " Findings: " + "; ".join(consolidated_causes) if consolidated_causes else " No major operational issues identified."
            )

            # Generate structured recommendation
            rec = await self.rec_service.create_recommendation(
                tenant_id=tenant_id,
                execution_id=exec_record.id,
                title=f"Strategic Recommendation for: {objective[:40]}",
                problem=f"Objective under review: {objective}",
                reasoning_summary=findings_summary,
                expected_benefit="Improved operational performance and decision clarity.",
                suggested_action="Review lead follow-up response times and resolve open incident tasks.",
                evidence=evidence_list,
                risk="LOW",
                confidence=0.85 if not has_partial_failure else 0.70,
                required_approval=needs_approval,
                approval_id=uuid.UUID(approval_id) if approval_id else None,
                priority="NORMAL",
            )
            recommendations_created.append(rec)

            # Calculate confidence
            overall_confidence = 0.90 if not has_partial_failure else 0.70

            # Determine final execution status
            final_status = AgentRequestStatus.COMPLETED
            if has_partial_failure and collected_results:
                final_status = AgentRequestStatus.PARTIAL
            elif has_partial_failure and not collected_results:
                final_status = AgentRequestStatus.FAILED

            # 5. Update persistent execution record
            exec_record.status = final_status.value
            exec_record.completed_at = datetime.now(timezone.utc)
            exec_record.agents_called = agents_called
            exec_record.tasks_created = tasks_created
            exec_record.recommendations = [r.model_dump(mode="json") for r in recommendations_created]
            exec_record.result = {
                "facts": consolidated_facts,
                "causes": consolidated_causes,
                "findings_summary": findings_summary,
                "confidence": overall_confidence,
            }
            exec_record.confidence = overall_confidence
            await self.session.commit()

            return AgentResult(
                request_id=f"req_{uuid.uuid4().hex[:12]}",
                agent="owner_ai",
                status=final_status,
                finding=findings_summary,
                evidence=evidence_list,
                recommendation=rec.suggested_action,
                confidence=overall_confidence,
                actions=[{"action": "consolidated_report", "facts": consolidated_facts, "causes": consolidated_causes}],
                needs_approval=needs_approval,
                approval_id=approval_id,
                correlation_id=correlation_id,
            )

        except Exception as exc:
            logger.error("Owner AI Orchestration error: %s", exc, exc_info=True)
            exec_record.status = "FAILED"
            exec_record.completed_at = datetime.now(timezone.utc)
            exec_record.error = str(exc)
            await self.session.commit()

            return AgentResult(
                request_id=f"req_{uuid.uuid4().hex[:12]}",
                agent="owner_ai",
                status=AgentRequestStatus.FAILED,
                error=f"Orchestration failure: {str(exc)}",
                correlation_id=correlation_id,
            )
