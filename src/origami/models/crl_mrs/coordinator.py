"""中文：CRL-MRS 基础协调器，用合作奖励和冲突惩罚调整 fleet 动作。

English: Basic CRL-MRS coordinator that adjusts fleet actions with cooperation rewards and conflict penalties.
"""

from __future__ import annotations

from typing import Any


class CRLMRSCoordinator:
    """Cooperative Reinforcement Learning for Multi-Robot Systems layer."""

    def __init__(self, alpha: float = 0.35, beta: float = 0.45) -> None:
        self.alpha = alpha
        self.beta = beta

    def coordinate(self, action: dict[str, Any]) -> dict[str, Any]:
        coordinated = dict(action)
        state = action.get("state", {})
        fleet_context = state.get("fleet_context", {})
        task_reward = float(action.get("grpo", {}).get("selected_advantage", 0.0))
        cooperation_events: list[str] = []
        conflict_events: list[str] = []
        adjustment = "none"

        if fleet_context.get("corridor_occupied") and action.get("move") != "hold":
            coordinated["move"] = "hold"
            coordinated["speed_mps"] = 0.0
            adjustment = "yield_corridor"
            cooperation_events.append("yield_corridor")

        if fleet_context.get("elevator_queue") and action.get("move") == "enter_elevator":
            coordinated["move"] = "hold"
            coordinated["speed_mps"] = 0.0
            adjustment = "stagger_elevator"
            cooperation_events.append("stagger_elevator")

        if fleet_context.get("same_elevator_conflict"):
            conflict_events.append("same_elevator_conflict")

        if fleet_context.get("deadlock_risk"):
            conflict_events.append("deadlock_risk")
            if coordinated.get("move") != "hold":
                coordinated["move"] = "hold"
                coordinated["speed_mps"] = 0.0
                adjustment = "avoid_deadlock"
                cooperation_events.append("avoid_deadlock")

        nearby = fleet_context.get("nearby_robots", 0)
        if nearby and adjustment == "none":
            adjustment = "aware"

        coordinated["fleet_adjustment"] = adjustment
        coordinated["crl_mrs"] = {
            "alpha": self.alpha,
            "beta": self.beta,
            "task_reward": task_reward,
            "cooperation_events": cooperation_events,
            "conflict_events": conflict_events,
            "meta_reward": self._meta_reward(task_reward, cooperation_events, conflict_events),
        }
        return coordinated

    def _meta_reward(
        self,
        task_reward: float,
        cooperation_events: list[str],
        conflict_events: list[str],
    ) -> float:
        cooperation_reward = len(cooperation_events) * 2.0
        conflict_penalty = len(conflict_events) * 8.0
        return task_reward + self.alpha * cooperation_reward - self.beta * conflict_penalty
