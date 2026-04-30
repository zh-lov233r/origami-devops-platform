"""中文：HTD-IRL 规划器，为 Carry & Go 生成分层任务图、候选动作和重规划轨迹。

English: HTD-IRL planner that creates Carry & Go task graphs, candidate actions, and re-plan traces.
"""

from __future__ import annotations

from typing import Any


class HTDIRLPlanner:
    """Hierarchical task decomposition with simple re-plan triggers."""

    def __init__(
        self,
        success_threshold: float = 0.70,
        battery_abort_pct: float = 12.0,
    ) -> None:
        self.success_threshold = success_threshold
        self.battery_abort_pct = battery_abort_pct

    def plan(self, state: dict[str, Any]) -> dict[str, Any]:
        planned = dict(state)
        mission_type = planned.get("mission_type", "carry_go_delivery")
        success_prob = float(planned.get("task_success_prob", 1.0))
        replan_reasons = self._replan_reasons(planned, success_prob)
        should_replan = bool(replan_reasons)

        if mission_type == "carry_go_delivery":
            task_graph = self._carry_go_task_graph(planned)
        else:
            task_graph = self._generic_task_graph()

        current_subtask = self._current_subtask(task_graph["level_2"], planned)
        task_status = self._task_status(task_graph["level_2"], current_subtask, planned)
        replan_level, route_strategy = self._replan_strategy(planned, replan_reasons)
        recovery_actions = self._recovery_actions(replan_level, replan_reasons, route_strategy)
        candidate_actions = self._candidate_actions(current_subtask, planned, route_strategy)

        planned["task_graph"] = task_graph
        planned["task_plan"] = task_graph["level_2"]
        planned["current_subtask"] = current_subtask
        planned["task_status"] = task_status
        planned["task_progress"] = self._task_progress(task_graph["level_2"], task_status)
        planned["replan_requested"] = should_replan
        planned["replan_level"] = replan_level
        planned["route_strategy"] = route_strategy
        planned["replan_reasons"] = replan_reasons
        planned["recovery_actions"] = recovery_actions
        planned["candidate_actions"] = candidate_actions
        planned["htd_irl"] = {
            "success_threshold": self.success_threshold,
            "task_success_prob": success_prob,
            "active_subtask": current_subtask,
            "task_depth": 3,
            "replan_reasons": replan_reasons,
            "replan_level": replan_level,
            "route_strategy": route_strategy,
            "recovery_actions": recovery_actions,
            "candidate_count": len(candidate_actions),
        }
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
                "localize": ["read_map", "match_landmarks", "confirm_pose"],
                "navigate_to_pickup": ["plan_path", "avoid_people", "avoid_blocked_corridors"],
                "verify_payload": ["scan_manifest", "check_weight", "check_lock"],
                "lock_payload": ["close_latch", "verify_lock", "record_payload_state"],
                "navigate_to_dropoff": ["plan_path", "yield_in_corridor", "respect_sla"],
                "request_elevator": ["check_queue", "reserve_car", "hold_at_safe_distance"],
                "ride_elevator": ["enter_car", "hold_centerline", "exit_at_floor"],
                "handoff_payload": ["stop", "unlock_payload", "record_confirmation"],
                "confirm_delivery": ["record_signature", "close_task", "sync_audit"],
            },
            "edges": HTDIRLPlanner._edges(level_2),
            "constraints": {
                "max_payload_kg": 10.0,
                "human_stop_distance_m": 0.30,
                "requires_handoff_auth": True,
                "requires_payload_lock": True,
            },
        }

    @staticmethod
    def _generic_task_graph() -> dict[str, Any]:
        level_2 = ["localize", "move_to_target", "verify_safe", "complete"]
        return {
            "level_1": "complete_task",
            "level_2": level_2,
            "level_3": {
                "localize": ["read_map", "match_landmarks"],
                "move_to_target": ["plan_path", "avoid_obstacles"],
                "verify_safe": ["check_uncertainty", "check_rules"],
                "complete": ["record_result"],
            },
            "edges": HTDIRLPlanner._edges(level_2),
            "constraints": {"human_stop_distance_m": 0.30},
        }

    @staticmethod
    def _current_subtask(level_2: list[str], state: dict[str, Any]) -> str:
        requested = state.get("current_subtask")
        if requested in level_2:
            return str(requested)

        completed = set(state.get("completed_subtasks", []))
        for subtask in level_2:
            if subtask not in completed:
                return subtask
        return level_2[-1]

    def _replan_reasons(self, state: dict[str, Any], success_prob: float) -> list[str]:
        reasons: list[str] = []
        if state.get("should_estop"):
            reasons.append("emergency_stop")
        if state.get("stum_gate") == "HIGH":
            reasons.append("high_uncertainty")
        if bool(state.get("should_replan")):
            reasons.append("stum_requested_replan")
        if success_prob < self.success_threshold:
            reasons.append("low_task_success_probability")
        if state.get("blocked_paths"):
            reasons.append("blocked_path")
        if float(state.get("battery_pct", 100.0)) <= self.battery_abort_pct:
            reasons.append("battery_abort")
        if state.get("payload_over_limit") or state.get("payload_mismatch"):
            reasons.append("payload_safety")
        if state.get("elevator_queue_unknown"):
            reasons.append("elevator_queue_unknown")
        return self._unique(reasons)

    def _replan_strategy(
        self,
        state: dict[str, Any],
        replan_reasons: list[str],
    ) -> tuple[int | None, str]:
        if not replan_reasons:
            return None, "normal"
        if any(reason in replan_reasons for reason in ("emergency_stop", "battery_abort", "payload_safety")):
            return 1, "safe_halt_or_return"
        if "blocked_path" in replan_reasons or state.get("stum_gate") == "HIGH":
            return 3, "alternate_route"
        if "elevator_queue_unknown" in replan_reasons:
            return 2, "elevator_wait"
        return 2, "workflow_recovery"

    @staticmethod
    def _task_status(
        level_2: list[str],
        current_subtask: str,
        state: dict[str, Any],
    ) -> dict[str, str]:
        completed = set(state.get("completed_subtasks", []))
        blocked = set(state.get("blocked_subtasks", []))
        status: dict[str, str] = {}
        for subtask in level_2:
            if subtask in completed:
                status[subtask] = "completed"
            elif subtask in blocked:
                status[subtask] = "blocked"
            elif subtask == current_subtask:
                status[subtask] = "active"
            else:
                status[subtask] = "pending"
        return status

    @staticmethod
    def _task_progress(level_2: list[str], task_status: dict[str, str]) -> float:
        if not level_2:
            return 0.0
        completed = sum(1 for subtask in level_2 if task_status.get(subtask) == "completed")
        return completed / len(level_2)

    @staticmethod
    def _candidate_actions(
        current_subtask: str,
        state: dict[str, Any],
        route_strategy: str,
    ) -> list[dict[str, Any]]:
        max_speed = float(state.get("max_speed_mps", 0.4))
        if route_strategy == "safe_halt_or_return":
            if float(state.get("battery_pct", 100.0)) <= 12.0:
                return [
                    {"move": "return_to_dock", "speed_mps": min(max_speed, 0.3)},
                    {"move": "hold", "speed_mps": 0.0},
                ]
            return [{"move": "hold", "speed_mps": 0.0}]

        if current_subtask in {"request_elevator", "ride_elevator"}:
            return [
                {"move": "enter_elevator", "speed_mps": min(max_speed, 0.2)},
                {"move": "hold", "speed_mps": 0.0},
            ]

        if current_subtask == "handoff_payload":
            return [
                {"move": "handoff_payload", "speed_mps": 0.0},
                {"move": "hold", "speed_mps": 0.0},
            ]

        if current_subtask in {"verify_payload", "lock_payload", "confirm_delivery", "localize"}:
            return [
                {"move": "hold", "speed_mps": 0.0},
                {"move": "east", "speed_mps": max_speed},
                {"move": "north", "speed_mps": max_speed},
                {"move": "south", "speed_mps": max_speed},
                {"move": "west", "speed_mps": max_speed},
            ]

        return [
            {"move": "east", "speed_mps": max_speed},
            {"move": "north", "speed_mps": max_speed},
            {"move": "south", "speed_mps": max_speed},
            {"move": "west", "speed_mps": max_speed},
            {"move": "hold", "speed_mps": 0.0},
        ]

    @staticmethod
    def _recovery_actions(
        replan_level: int | None,
        replan_reasons: list[str],
        route_strategy: str,
    ) -> list[str]:
        if replan_level is None:
            return []
        if route_strategy == "safe_halt_or_return":
            if "battery_abort" in replan_reasons:
                return ["return_to_dock", "notify_operator"]
            return ["hold", "request_operator_review"]
        if route_strategy == "alternate_route":
            return ["mark_blocked_path", "sample_alternate_route", "publish_updated_plan"]
        if route_strategy == "elevator_wait":
            return ["refresh_elevator_queue", "reserve_next_car", "hold_at_safe_distance"]
        return ["retry_current_subtask", "refresh_task_context"]

    @staticmethod
    def _edges(level_2: list[str]) -> list[dict[str, str]]:
        return [
            {"from": source, "to": target}
            for source, target in zip(level_2, level_2[1:], strict=False)
        ]

    @staticmethod
    def _unique(items: list[str]) -> list[str]:
        unique_items: list[str] = []
        for item in items:
            if item not in unique_items:
                unique_items.append(item)
        return unique_items
