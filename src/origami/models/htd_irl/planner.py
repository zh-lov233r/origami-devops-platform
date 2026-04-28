"""中文：HTD-IRL 基础规划器，为 Carry & Go 和通用任务生成三层任务计划。

English: Basic HTD-IRL planner that creates three-level task plans for Carry & Go and generic missions.
"""

from __future__ import annotations

from typing import Any


class HTDIRLPlanner:
    """Hierarchical task decomposition with simple re-plan triggers."""

    def __init__(self, success_threshold: float = 0.70) -> None:
        self.success_threshold = success_threshold

    def plan(self, state: dict[str, Any]) -> dict[str, Any]:
        planned = dict(state)
        mission_type = planned.get("mission_type", "carry_go_delivery")
        success_prob = float(planned.get("task_success_prob", 1.0))
        blocked_paths = planned.get("blocked_paths", [])
        should_replan = bool(planned.get("should_replan")) or success_prob < self.success_threshold

        if mission_type == "carry_go_delivery":
            task_graph = self._carry_go_task_graph(planned)
        else:
            task_graph = self._generic_task_graph()

        route_strategy = "normal"
        replan_level = None
        if should_replan:
            replan_level = 3 if blocked_paths or planned.get("stum_gate") == "HIGH" else 2
            route_strategy = "alternate_route" if replan_level == 3 else "workflow_recovery"

        planned["task_graph"] = task_graph
        planned["task_plan"] = task_graph["level_2"]
        planned["current_subtask"] = self._current_subtask(task_graph["level_2"], planned)
        planned["replan_requested"] = should_replan
        planned["replan_level"] = replan_level
        planned["route_strategy"] = route_strategy
        return planned

    @staticmethod
    def _carry_go_task_graph(state: dict[str, Any]) -> dict[str, Any]:
        carrying_payload = bool(state.get("payload_loaded", False))
        elevator_required = bool(state.get("elevator_required", False))

        level_2 = ["localize", "navigate_to_pickup", "verify_payload", "lock_payload"]
        if carrying_payload:
            level_2 = ["localize", "verify_payload", "navigate_to_dropoff"]
        if elevator_required:
            level_2.append("request_elevator")
            level_2.append("ride_elevator")
        level_2.extend(["handoff_payload", "confirm_delivery"])

        return {
            "level_1": "deliver_payload",
            "level_2": level_2,
            "level_3": {
                "navigate_to_pickup": ["plan_path", "avoid_people", "avoid_blocked_corridors"],
                "verify_payload": ["scan_manifest", "check_weight", "check_lock"],
                "navigate_to_dropoff": ["plan_path", "yield_in_corridor", "respect_sla"],
                "request_elevator": ["check_queue", "reserve_car", "hold_at_safe_distance"],
                "handoff_payload": ["stop", "unlock_payload", "record_confirmation"],
            },
        }

    @staticmethod
    def _generic_task_graph() -> dict[str, Any]:
        return {
            "level_1": "complete_task",
            "level_2": ["localize", "move_to_target", "verify_safe", "complete"],
            "level_3": {
                "move_to_target": ["plan_path", "avoid_obstacles"],
                "verify_safe": ["check_uncertainty", "check_rules"],
            },
        }

    @staticmethod
    def _current_subtask(level_2: list[str], state: dict[str, Any]) -> str:
        requested = state.get("current_subtask")
        if requested in level_2:
            return str(requested)
        return level_2[0]
