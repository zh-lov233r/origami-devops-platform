"""中文：HTD-IRL 规划器占位实现，为当前状态生成层级任务计划。

English: Placeholder HTD-IRL planner implementation that produces a hierarchical task plan for the current state.
"""

from __future__ import annotations

from typing import Any


class HTDIRLPlanner:
    """Placeholder hierarchical task planner."""

    def plan(self, state: dict[str, Any]) -> dict[str, Any]:
        planned = dict(state)
        planned["task_plan"] = ["localize", "move_to_target", "verify_safe"]
        return planned
