import uuid
from typing import Dict
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.business_profile import BusinessProfile
from app.database.models.product import Product
from app.database.models.knowledge import KnowledgeCategory
from app.database.models.guardrail import AIGuardrail
from app.database.models.workflow import WorkflowConfiguration


class TenantValidatorEngine:
    """Deterministic validator engine checking actual database records for a tenant."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def validate_all(self, tenant_id: uuid.UUID) -> Dict[str, bool]:
        """Runs all deterministic checks for a tenant and returns a dict mapping checklist key to bool."""
        results: Dict[str, bool] = {}

        # 1. Business Profile Checks
        bp_stmt = select(BusinessProfile).where(BusinessProfile.tenant_id == tenant_id)
        bp = (await self.session.execute(bp_stmt)).scalar_one_or_none()

        if bp is not None:
            results["business_profile_completed"] = bool(bp.business_name and bp.business_name.strip())
            results["business_description_completed"] = bool(bp.description and bp.description.strip())
            results["operating_hours_configured"] = bool(bp.operating_hours and isinstance(bp.operating_hours, dict) and len(bp.operating_hours) > 0)
            results["payment_methods_configured"] = bool(bp.payment_methods and isinstance(bp.payment_methods, dict) and len(bp.payment_methods) > 0)
            results["shipping_information_configured"] = bool(bp.shipping_information and isinstance(bp.shipping_information, dict) and len(bp.shipping_information) > 0)
            results["return_policy_configured"] = bool(bp.return_policy and bp.return_policy.strip())
            results["exchange_policy_configured"] = bool(bp.exchange_policy and bp.exchange_policy.strip())
            results["refund_policy_configured"] = bool(bp.refund_policy and bp.refund_policy.strip())
        else:
            results["business_profile_completed"] = False
            results["business_description_completed"] = False
            results["operating_hours_configured"] = False
            results["payment_methods_configured"] = False
            results["shipping_information_configured"] = False
            results["return_policy_configured"] = False
            results["exchange_policy_configured"] = False
            results["refund_policy_configured"] = False

        # 2. Product Catalog Checks
        prod_stmt = select(Product).where(Product.tenant_id == tenant_id, Product.is_active.is_(True))
        products = (await self.session.execute(prod_stmt)).scalars().all()

        results["product_configured"] = len(products) > 0
        results["product_pricing_configured"] = len(products) > 0 and all(p.price is not None and p.price > 0 for p in products)
        results["product_stock_configured"] = len(products) > 0 and all(p.stock is not None and p.stock >= 0 for p in products)

        # 3. Knowledge Base Checks
        kc_count_stmt = select(func.count(KnowledgeCategory.id)).where(
            KnowledgeCategory.tenant_id == tenant_id, KnowledgeCategory.is_active.is_(True)
        )
        kc_count = (await self.session.execute(kc_count_stmt)).scalar() or 0
        results["ai_knowledge_configured"] = kc_count >= 10

        # 4. AI Guardrails Checks
        gr_count_stmt = select(func.count(AIGuardrail.id)).where(
            AIGuardrail.tenant_id == tenant_id, AIGuardrail.is_enabled.is_(True)
        )
        gr_count = (await self.session.execute(gr_count_stmt)).scalar() or 0
        results["ai_guardrails_initialized"] = gr_count >= 11

        # 5. Workflow Configurations Checks
        wf_count_stmt = select(func.count(WorkflowConfiguration.id)).where(
            WorkflowConfiguration.tenant_id == tenant_id, WorkflowConfiguration.is_active.is_(True)
        )
        wf_count = (await self.session.execute(wf_count_stmt)).scalar() or 0
        results["default_workflow_initialized"] = wf_count >= 3

        # 6. Integrations & Operational Checks
        results["whatsapp_integration_available"] = True  # System channel configuration available

        # Human handoff is available if workflow configuration for HUMAN_HANDOFF exists
        hh_wf_stmt = select(WorkflowConfiguration).where(
            WorkflowConfiguration.tenant_id == tenant_id,
            WorkflowConfiguration.key == "HUMAN_HANDOFF",
            WorkflowConfiguration.is_active.is_(True),
        )
        hh_wf = (await self.session.execute(hh_wf_stmt)).scalar_one_or_none()
        results["human_handoff_available"] = hh_wf is not None

        # 7. Overall Validation Check
        # tenant_configuration_validated is True if core required items (profile, products, knowledge, guardrails, workflows, handoff) are True
        core_keys = [
            "business_profile_completed",
            "product_configured",
            "product_pricing_configured",
            "ai_knowledge_configured",
            "ai_guardrails_initialized",
            "default_workflow_initialized",
            "human_handoff_available",
        ]
        results["tenant_configuration_validated"] = all(results.get(k, False) for k in core_keys)

        return results
