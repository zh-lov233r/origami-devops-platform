"""中文：GRPO 基础策略模块，对候选动作做群组相对评分并选择最佳动作。

English: Basic GRPO policy module that scores candidate actions with group-relative advantages.
"""

from __future__ import annotations

from math import sqrt
from typing import Any


class GRPOPolicy:
    """Small explainable Group Relative Policy Optimisation inference layer."""

    def __init__(self, group_size: int = 16, max_speed_mps: float = 0.4) -> None:
        self.group_size = group_size
        self.max_speed_mps = max_speed_mps

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        candidates = self._candidate_actions(state)[: self.group_size]
        scored = [{**candidate, "score": self._score(candidate, state)} for candidate in candidates]
        rewards = [candidate["score"] for candidate in scored]
        mean_reward = sum(rewards) / len(rewards)
        variance = sum((reward - mean_reward) ** 2 for reward in rewards) / len(rewards)
        std_reward = sqrt(variance) or 1.0

        for candidate in scored:
            candidate["advantage"] = (candidate["score"] - mean_reward) / std_reward

        selected = max(scored, key=lambda candidate: candidate["advantage"])
        if state.get("stum_gate") == "HIGH":
            selected = {
                "move": "hold",
                "speed_mps": 0.0,
                "reason": "stum_high_uncertainty",
                "score": min(rewards),
                "advantage": min(candidate["advantage"] for candidate in scored),
            }

        return {
            "move": selected["move"],
            "speed_mps": selected.get("speed_mps", self.max_speed_mps),
            "confidence": max(0.0, 1.0 - float(state.get("sigma_total", 0.0))),
            "grpo": {
                "group_size": len(scored),
                "mean_reward": mean_reward,
                "std_reward": std_reward,
                "selected_advantage": selected["advantage"],
                "candidates": scored,
            },
            "state": state,
        }

    def _candidate_actions(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        explicit = state.get("candidate_actions")
        if isinstance(explicit, list) and explicit:
            return explicit

        return [
            {"move": "east", "speed_mps": self.max_speed_mps},
            {"move": "north", "speed_mps": self.max_speed_mps},
            {"move": "south", "speed_mps": self.max_speed_mps},
            {"move": "west", "speed_mps": self.max_speed_mps},
            {"move": "hold", "speed_mps": 0.0},
        ]

    def _score(self, candidate: dict[str, Any], state: dict[str, Any]) -> float:
        score = 0.0
        score += self._distance_delta(candidate.get("move", "hold"), state) * 2.0
        score += 0.2 if state.get("route_strategy") == "normal" else 0.05
        score -= float(state.get("sigma_total", 0.0)) * 0.8

        if candidate.get("move") == "hold":
            score -= 0.2
            if state.get("stum_gate") == "HIGH":
                score += 2.0

        if state.get("battery_pct", 100) <= 15:
            score += 1.0 if candidate.get("move") == "return_to_dock" else -0.6

        fleet_context = state.get("fleet_context", {})
        if fleet_context.get("corridor_occupied") and candidate.get("move") != "hold":
            score -= 1.0
        if fleet_context.get("elevator_queue") and candidate.get("move") == "enter_elevator":
            score -= 1.0

        return score

    @staticmethod
    def _distance_delta(move: str, state: dict[str, Any]) -> float:
        position = state.get("position")
        target = state.get("target")
        if not (
            isinstance(position, list)
            and isinstance(target, list)
            and len(position) >= 2
            and len(target) >= 2
        ):
            return 0.0

        x, y = float(position[0]), float(position[1])
        tx, ty = float(target[0]), float(target[1])
        next_x, next_y = x, y
        if move == "east":
            next_x += 1
        elif move == "west":
            next_x -= 1
        elif move == "north":
            next_y += 1
        elif move == "south":
            next_y -= 1

        before = abs(tx - x) + abs(ty - y)
        after = abs(tx - next_x) + abs(ty - next_y)
        return before - after
