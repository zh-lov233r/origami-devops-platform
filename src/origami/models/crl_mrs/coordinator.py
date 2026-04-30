"""中文：CRL-MRS 协调器，用资源冲突、优先级和合作奖励调整 fleet 动作。

English: CRL-MRS coordinator that adjusts fleet actions with resource conflicts, priorities, and cooperation rewards.
"""

from __future__ import annotations

from typing import Any


class CRLMRSCoordinator:
    """Cooperative Reinforcement Learning for Multi-Robot Systems layer."""

    def __init__(
        self,
        alpha: float = 0.35,
        beta: float = 0.45,
        priority_weight: float = 0.20,
        resource_weight: float = 0.25,
    ) -> None:
        self.alpha = alpha
        self.beta = beta
        self.priority_weight = priority_weight
        self.resource_weight = resource_weight

    def coordinate(self, action: dict[str, Any]) -> dict[str, Any]:
        coordinated = dict(action)
        state = action.get("state", {})
        fleet_context = state.get("fleet_context", {})
        task_reward = float(action.get("grpo", {}).get("selected_advantage", 0.0))
        priority_score = self._priority_score(action, state, fleet_context)
        resource_request = self._resource_request(action, state)
        conflict_graph = self._conflict_graph(resource_request, fleet_context)
        cooperation_events: list[str] = []
        conflict_events: list[str] = []
        resource_events: list[str] = []
        adjustment = "none"

        if self._should_yield_corridor(action, fleet_context, priority_score):
            coordinated["move"] = "hold"
            coordinated["speed_mps"] = 0.0
            adjustment = "yield_corridor"
            cooperation_events.append("yield_corridor")
            conflict_events.append("corridor_conflict")

        if self._can_claim_corridor(action, fleet_context, priority_score):
            adjustment = "claim_corridor_priority"
            resource_events.append("claim_corridor")

        if fleet_context.get("elevator_queue") and action.get("move") == "enter_elevator":
            coordinated["move"] = "hold"
            coordinated["speed_mps"] = 0.0
            adjustment = "stagger_elevator"
            cooperation_events.append("stagger_elevator")
            conflict_events.append("elevator_queue")

        if fleet_context.get("same_elevator_conflict"):
            conflict_events.append("same_elevator_conflict")
            if action.get("move") == "enter_elevator":
                coordinated["move"] = "hold"
                coordinated["speed_mps"] = 0.0
                adjustment = "avoid_elevator_conflict"
                cooperation_events.append("avoid_elevator_conflict")

        if fleet_context.get("deadlock_risk"):
            conflict_events.append("deadlock_risk")
            if coordinated.get("move") != "hold":
                coordinated["move"] = "hold"
                coordinated["speed_mps"] = 0.0
                adjustment = "avoid_deadlock"
                cooperation_events.append("avoid_deadlock")

        if fleet_context.get("dock_queue") and action.get("move") == "return_to_dock":
            coordinated["move"] = "hold"
            coordinated["speed_mps"] = 0.0
            adjustment = "wait_for_dock_slot"
            cooperation_events.append("wait_for_dock_slot")
            conflict_events.append("dock_queue")

        nearby = fleet_context.get("nearby_robots", 0)
        if nearby and adjustment == "none":
            adjustment = "aware"

        reservation_request = self._reservation_request(
            coordinated,
            state,
            resource_request,
            priority_score,
            adjustment,
        )
        meta_reward, meta_breakdown = self._meta_reward(
            task_reward=task_reward,
            cooperation_events=cooperation_events,
            conflict_events=conflict_events,
            priority_score=priority_score,
            resource_events=resource_events,
        )

        coordinated["fleet_adjustment"] = adjustment
        coordinated["fleet_priority_score"] = priority_score
        coordinated["reservation_request"] = reservation_request
        coordinated["crl_mrs"] = {
            "alpha": self.alpha,
            "beta": self.beta,
            "priority_weight": self.priority_weight,
            "resource_weight": self.resource_weight,
            "task_reward": task_reward,
            "priority_score": priority_score,
            "resource_request": resource_request,
            "reservation_request": reservation_request,
            "conflict_graph": conflict_graph,
            "cooperation_events": cooperation_events,
            "conflict_events": conflict_events,
            "resource_events": resource_events,
            "meta_reward": meta_reward,
            "meta_reward_breakdown": meta_breakdown,
            "coordination_policy": "crl-mrs-carry-go-v0",
        }
        return coordinated

    def _meta_reward(
        self,
        task_reward: float,
        cooperation_events: list[str],
        conflict_events: list[str],
        priority_score: float,
        resource_events: list[str],
    ) -> tuple[float, dict[str, float]]:
        cooperation_reward = len(cooperation_events) * 2.0
        conflict_penalty = len(conflict_events) * 8.0
        resource_reward = len(resource_events) * 1.5
        priority_reward = priority_score
        meta_reward = (
            task_reward
            + self.alpha * cooperation_reward
            - self.beta * conflict_penalty
            + self.priority_weight * priority_reward
            + self.resource_weight * resource_reward
        )
        return meta_reward, {
            "task_reward": task_reward,
            "cooperation_reward": cooperation_reward,
            "conflict_penalty": conflict_penalty,
            "priority_reward": priority_reward,
            "resource_reward": resource_reward,
        }

    @staticmethod
    def _resource_request(action: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        move = action.get("move")
        current_subtask = state.get("current_subtask")
        if move == "enter_elevator" or current_subtask in {"request_elevator", "ride_elevator"}:
            return {"resource": "elevator", "mode": "exclusive", "ttl_s": 30.0}
        if move in {"east", "north", "south", "west"}:
            return {"resource": "corridor", "mode": "shared", "ttl_s": 5.0}
        if move == "return_to_dock":
            return {"resource": "dock", "mode": "exclusive", "ttl_s": 60.0}
        return {"resource": "none", "mode": "none", "ttl_s": 0.0}

    @staticmethod
    def _conflict_graph(
        resource_request: dict[str, Any],
        fleet_context: dict[str, Any],
    ) -> dict[str, Any]:
        conflicts: list[dict[str, Any]] = []
        resource = resource_request.get("resource")
        if resource == "corridor" and fleet_context.get("corridor_occupied"):
            conflicts.append(
                {
                    "resource": "corridor",
                    "with": fleet_context.get("corridor_occupied_by", "unknown"),
                    "type": "occupancy",
                }
            )
        if resource == "elevator" and fleet_context.get("elevator_queue"):
            conflicts.append(
                {
                    "resource": "elevator",
                    "with": fleet_context.get("elevator_queue", "queue"),
                    "type": "queue",
                }
            )
        if fleet_context.get("same_elevator_conflict"):
            conflicts.append(
                {
                    "resource": "elevator",
                    "with": fleet_context.get("same_elevator_conflict_with", "unknown"),
                    "type": "exclusive_conflict",
                }
            )
        if resource == "dock" and fleet_context.get("dock_queue"):
            conflicts.append({"resource": "dock", "with": "dock_queue", "type": "queue"})
        return {"requested_resource": resource, "conflicts": conflicts}

    def _priority_score(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
        fleet_context: dict[str, Any],
    ) -> float:
        base_priority = float(state.get("task_priority", fleet_context.get("task_priority", 1.0)))
        deadline_slack_s = float(state.get("deadline_slack_s", fleet_context.get("deadline_slack_s", 300.0)))
        urgency = max(0.0, min(1.0, (300.0 - deadline_slack_s) / 300.0))
        safety_bonus = 1.0 if action.get("move") in {"hold", "return_to_dock"} else 0.0
        payload_bonus = 0.5 if state.get("payload_kg", 0.0) else 0.0
        return round(base_priority + urgency + safety_bonus + payload_bonus, 6)

    @staticmethod
    def _should_yield_corridor(
        action: dict[str, Any],
        fleet_context: dict[str, Any],
        priority_score: float,
    ) -> bool:
        if not fleet_context.get("corridor_occupied") or action.get("move") == "hold":
            return False
        peer_priority = float(fleet_context.get("corridor_peer_priority", priority_score + 1.0))
        return priority_score <= peer_priority

    @staticmethod
    def _can_claim_corridor(
        action: dict[str, Any],
        fleet_context: dict[str, Any],
        priority_score: float,
    ) -> bool:
        if not fleet_context.get("corridor_occupied") or action.get("move") == "hold":
            return False
        peer_priority = float(fleet_context.get("corridor_peer_priority", priority_score + 1.0))
        return priority_score > peer_priority

    @staticmethod
    def _reservation_request(
        action: dict[str, Any],
        state: dict[str, Any],
        resource_request: dict[str, Any],
        priority_score: float,
        adjustment: str,
    ) -> dict[str, Any]:
        robot_id = state.get("robot_id", "local")
        resource = resource_request.get("resource", "none")
        if action.get("move") == "hold" and adjustment not in {"claim_corridor_priority", "none", "aware"}:
            status = "deferred"
        elif resource == "none":
            status = "none"
        else:
            status = "requested"
        return {
            "robot_id": robot_id,
            "resource": resource,
            "mode": resource_request.get("mode", "none"),
            "priority_score": priority_score,
            "status": status,
            "ttl_s": resource_request.get("ttl_s", 0.0),
        }
