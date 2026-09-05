from typing import Any


def get_nested_value(data: dict[str, Any], path: str) -> Any:
    """Extract nested value from dict using dot notation, e.g. 'order.total'."""
    parts = path.split(".")
    curr: Any = data
    for part in parts:
        if isinstance(curr, dict) and part in curr:
            curr = curr[part]
        else:
            return None
    return curr


class ConditionEvaluator:
    """Deterministic evaluation of workflow conditions."""

    OPERATORS = {
        "equals": lambda field_val, target: field_val == target,
        "not_equals": lambda field_val, target: field_val != target,
        "greater_than": lambda field_val, target: field_val is not None and field_val > target,
        "less_than": lambda field_val, target: field_val is not None and field_val < target,
        "greater_or_equal": lambda field_val, target: field_val is not None and field_val >= target,
        "less_or_equal": lambda field_val, target: field_val is not None and field_val <= target,
        "exists": lambda field_val, target: field_val is not None,
        "not_exists": lambda field_val, target: field_val is None,
        "contains": lambda field_val, target: field_val is not None and target in field_val,
    }

    @classmethod
    def evaluate_condition(cls, condition: dict[str, Any], context: dict[str, Any]) -> bool:
        """Evaluate single condition or logical group (AND / OR)."""
        if "AND" in condition:
            sub_conds = condition["AND"]
            return all(cls.evaluate_condition(c, context) for c in sub_conds)

        if "OR" in condition:
            sub_conds = condition["OR"]
            return any(cls.evaluate_condition(c, context) for c in sub_conds)

        field_path = condition.get("field")
        op = condition.get("operator")
        expected_val = condition.get("value")

        if not field_path or not op:
            return True

        if op not in cls.OPERATORS:
            raise ValueError(f"Unsupported condition operator: {op}")

        actual_val = get_nested_value(context, field_path)
        return cls.OPERATORS[op](actual_val, expected_val)

    @classmethod
    def evaluate_conditions(cls, conditions: list[dict[str, Any]] | None, context: dict[str, Any]) -> bool:
        """Evaluate a list of top-level conditions with implicit AND logic."""
        if not conditions:
            return True
        return all(cls.evaluate_condition(c, context) for c in conditions)
