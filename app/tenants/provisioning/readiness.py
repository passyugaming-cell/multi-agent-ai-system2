from typing import Sequence, Dict, Any
from app.database.models.onboarding import OnboardingChecklist
from app.tenants.provisioning.schemas import ReadinessResultSchema, ReadinessCategoryScore

# Category Weights (Total = 100%)
CATEGORY_WEIGHTS: Dict[str, float] = {
    "Business Profile": 20.0,
    "Products": 20.0,
    "Knowledge": 15.0,
    "Policies": 15.0,
    "AI Guardrails": 10.0,
    "Operational Configuration": 10.0,
    "Integration Readiness": 10.0,
}


class ReadinessCalculator:
    """Deterministic calculator for evaluating tenant readiness score."""

    @staticmethod
    def calculate(
        checklist_items: Sequence[OnboardingChecklist],
        validation_results: Dict[str, bool] | None = None,
    ) -> ReadinessResultSchema:
        """Calculate readiness score, category breakdowns, blocking items, and readiness status.

        DO NOT ask AI/Gemini. This must be 100% deterministic logic.
        """
        if validation_results is None:
            validation_results = {}

        category_items: Dict[str, list[OnboardingChecklist]] = {cat: [] for cat in CATEGORY_WEIGHTS}
        completed_requirements: list[str] = []
        incomplete_requirements: list[str] = []
        blocking_requirements: list[str] = []

        for item in checklist_items:
            cat = item.category
            if cat not in category_items:
                category_items[cat] = []
            category_items[cat].append(item)

            # Determine item completion status either from DB item status or validator override
            is_valid = validation_results.get(item.key, item.status == "COMPLETED")

            if is_valid:
                completed_requirements.append(item.key)
            else:
                incomplete_requirements.append(item.key)
                if item.required:
                    blocking_requirements.append(item.key)

        # Calculate category scores
        total_score = 0.0
        category_scores: Dict[str, float] = {}

        for cat, weight in CATEGORY_WEIGHTS.items():
            items_in_cat = category_items.get(cat, [])
            if not items_in_cat:
                category_scores[cat] = 0.0
                continue

            completed_in_cat = 0
            for item in items_in_cat:
                is_valid = validation_results.get(item.key, item.status == "COMPLETED")
                if is_valid:
                    completed_in_cat += 1

            cat_ratio = completed_in_cat / len(items_in_cat)
            cat_score = round(cat_ratio * weight, 2)
            category_scores[cat] = cat_score
            total_score += cat_score

        overall_score = round(min(100.0, max(0.0, total_score)), 2)

        # Determine readiness status:
        # READY requires: score >= 90.0 AND no blocking requirements
        if overall_score >= 90.0 and len(blocking_requirements) == 0:
            status = "READY"
        elif overall_score >= 60.0:
            status = "NEARLY_READY"
        else:
            status = "NOT_READY"

        return ReadinessResultSchema(
            score=overall_score,
            percentage=overall_score,
            completed_requirements=completed_requirements,
            incomplete_requirements=incomplete_requirements,
            blocking_requirements=blocking_requirements,
            category_scores=category_scores,
            readiness_status=status,
        )
