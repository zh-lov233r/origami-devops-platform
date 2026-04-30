"""中文：GRPO 策略模块，对 Carry & Go 候选动作做群组相对评分和风险感知选择。

English: GRPO policy module that scores Carry & Go candidates with group-relative and risk-aware selection.
"""

from __future__ import annotations

from math import exp, sqrt
from typing import Any


class GRPOPolicy:
    """Small explainable Group Relative Policy Optimisation inference layer."""

    def __init__(
        self,
        group_size: int = 16,
        max_speed_mps: float = 0.4,
        rollout_horizon: int = 3,
        temperature: float = 0.35,
        low_battery_pct: float = 15.0,
    ) -> None:
        self.group_size = group_size
        self.max_speed_mps = max_speed_mps
        self.rollout_horizon = rollout_horizon
        self.temperature = temperature
        self.low_battery_pct = low_battery_pct

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        candidates = self._candidate_actions(state)[: self.group_size]
        scored = [self._score_candidate(candidate, state) for candidate in candidates]
        rewards = [candidate["score"] for candidate in scored]
        mean_reward = sum(rewards) / len(rewards)
        variance = sum((reward - mean_reward) ** 2 for reward in rewards) / len(rewards)
        std_reward = sqrt(variance) or 1.0

        for candidate in scored:
            candidate["advantage"] = (candidate["score"] - mean_reward) / std_reward

        probabilities = self._softmax([candidate["score"] for candidate in scored])
        for candidate, probability in zip(scored, probabilities, strict=True):
            candidate["probability"] = probability

        selected = max(scored, key=lambda candidate: candidate["advantage"])
        override_reason = None
        if state.get("stum_gate") == "HIGH" or state.get("should_estop"):
            selected = {
                "move": "hold",
                "speed_mps": 0.0,
                "reason": "stum_high_uncertainty",
                "score": min(rewards),
                "advantage": min(candidate["advantage"] for candidate in scored),
                "probability": 0.0,
                "reward_breakdown": {"uncertainty_penalty": -2.0, "safety_hold": 2.0},
                "rollout": self._rollout({"move": "hold", "speed_mps": 0.0}, state),
            }
            override_reason = "stum_high_uncertainty"

        return {
            "move": selected["move"],
            "speed_mps": selected.get("speed_mps", self.max_speed_mps),
            "confidence": max(0.0, 1.0 - float(state.get("sigma_total", 0.0))),
            "grpo": {
                "group_size": len(scored),
                "mean_reward": mean_reward,
                "std_reward": std_reward,
                "selected_advantage": selected["advantage"],
                "selected_score": selected["score"],
                "selected_probability": selected.get("probability", 0.0),
                "selected_reason": override_reason or selected.get("reason", "max_advantage"),
                "selected_breakdown": selected.get("reward_breakdown", {}),
                "selected_rollout": selected.get("rollout", {}),
                "action_distribution": {
                    candidate["id"]: candidate["probability"]
                    for candidate in scored
                },
                "risk_flags": self._risk_flags(state),
                "candidates": scored,
            },
            "state": state,
        }

    def _candidate_actions(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        explicit = state.get("candidate_actions")
        if isinstance(explicit, list) and explicit:
            return self._dedupe_candidates(
                [self._normalize_candidate(candidate) for candidate in explicit]
                + [{"move": "hold", "speed_mps": 0.0}]
            )

        candidates = [
            {"move": "east", "speed_mps": self.max_speed_mps},
            {"move": "north", "speed_mps": self.max_speed_mps},
            {"move": "south", "speed_mps": self.max_speed_mps},
            {"move": "west", "speed_mps": self.max_speed_mps},
            {"move": "hold", "speed_mps": 0.0},
        ]
        if float(state.get("battery_pct", 100.0)) <= self.low_battery_pct:
            candidates.append({"move": "return_to_dock", "speed_mps": min(self.max_speed_mps, 0.3)})
        if self._needs_elevator_action(state):
            candidates.append({"move": "enter_elevator", "speed_mps": min(self.max_speed_mps, 0.2)})
        if state.get("current_subtask") == "handoff_payload":
            candidates.append({"move": "handoff_payload", "speed_mps": 0.0})
        return self._dedupe_candidates(candidates)

    def _score_candidate(self, candidate: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_candidate(candidate)
        move = normalized["move"]
        rollout = self._rollout(normalized, state)
        breakdown = self._reward_breakdown(normalized, state, rollout)
        score = sum(breakdown.values())
        return {
            **normalized,
            "id": self._candidate_id(normalized),
            "score": score,
            "reward_breakdown": breakdown,
            "rollout": rollout,
            "reason": self._reason(move, state, breakdown),
        }

    def _reward_breakdown(
        self,
        candidate: dict[str, Any],
        state: dict[str, Any],
        rollout: dict[str, float],
    ) -> dict[str, float]:
        move = candidate.get("move", "hold")
        speed = float(candidate.get("speed_mps", self.max_speed_mps))
        sigma_total = float(state.get("sigma_total", 0.0))
        route_strategy = state.get("route_strategy", "normal")
        speed_scale = float(state.get("speed_scale", 1.0))

        breakdown = {
            "progress": self._distance_delta(move, state) * 2.0,
            "task_alignment": self._task_alignment(move, state),
            "route_quality": 0.25 if route_strategy == "normal" else 0.05,
            "uncertainty_penalty": -sigma_total * (1.2 if move != "hold" else 0.4),
            "speed_penalty": -max(0.0, speed - self.max_speed_mps * speed_scale) * 1.5,
            "energy": self._energy_reward(move, state),
            "fleet": self._fleet_reward(move, state),
            "payload": self._payload_reward(move, state),
            "human_safety": self._human_safety_reward(move, state),
            "rollout_value": float(rollout["value"]),
        }

        if move == "hold":
            breakdown["idle_cost"] = -0.2
            if state.get("stum_gate") in {"MEDIUM", "HIGH"}:
                breakdown["uncertainty_hold_bonus"] = 0.8

        return breakdown

    def _task_alignment(self, move: str, state: dict[str, Any]) -> float:
        current_subtask = state.get("current_subtask")
        if current_subtask in {"request_elevator", "ride_elevator"}:
            if move == "enter_elevator" and not state.get("elevator_queue_unknown"):
                return 0.9
            if move == "hold":
                return 0.2
            return -0.4
        if current_subtask == "handoff_payload":
            if move == "handoff_payload" and state.get("recipient_authenticated"):
                return 1.0
            if move == "handoff_payload":
                return -1.0
            if move == "hold":
                return 0.3
        if current_subtask in {"verify_payload", "lock_payload"} and move == "hold":
            return 0.2
        return 0.0

    def _energy_reward(self, move: str, state: dict[str, Any]) -> float:
        battery_pct = float(state.get("battery_pct", 100.0))
        if battery_pct <= self.low_battery_pct:
            return 1.8 if move == "return_to_dock" else -1.2
        if move == "return_to_dock":
            return -0.4
        return -0.02

    @staticmethod
    def _fleet_reward(move: str, state: dict[str, Any]) -> float:
        fleet_context = state.get("fleet_context", {})
        score = 0.0
        if fleet_context.get("corridor_occupied"):
            score += 0.4 if move == "hold" else -1.0
        if fleet_context.get("deadlock_risk"):
            score += 0.6 if move == "hold" else -1.2
        if fleet_context.get("elevator_queue") and move == "enter_elevator":
            score -= 1.0
        if fleet_context.get("same_elevator_conflict") and move == "enter_elevator":
            score -= 1.2
        return score

    @staticmethod
    def _payload_reward(move: str, state: dict[str, Any]) -> float:
        if state.get("payload_over_limit") or state.get("payload_mismatch"):
            return 1.0 if move == "hold" else -2.5
        if state.get("payload_kg", 0.0) and not state.get("payload_locked", True):
            return 0.4 if move == "hold" else -1.0
        return 0.0

    @staticmethod
    def _human_safety_reward(move: str, state: dict[str, Any]) -> float:
        nearest_human = float(state.get("nearest_human_distance_m", 999.0))
        if nearest_human < 0.3:
            return 1.0 if move == "hold" else -2.0
        if nearest_human < 0.8 and move != "hold":
            return -0.5
        return 0.0

    def _rollout(self, candidate: dict[str, Any], state: dict[str, Any]) -> dict[str, float]:
        position = state.get("position")
        target = state.get("target")
        if not (
            isinstance(position, list)
            and isinstance(target, list)
            and len(position) >= 2
            and len(target) >= 2
        ):
            return {
                "horizon": float(self.rollout_horizon),
                "distance_before": 0.0,
                "distance_after": 0.0,
                "progress": 0.0,
                "energy_cost": 0.0,
                "value": 0.0,
            }

        x, y = float(position[0]), float(position[1])
        tx, ty = float(target[0]), float(target[1])
        before = abs(tx - x) + abs(ty - y)
        move = str(candidate.get("move", "hold"))
        speed = float(candidate.get("speed_mps", self.max_speed_mps))
        for step in range(max(1, self.rollout_horizon)):
            step_move = move if step == 0 else self._greedy_move(x, y, tx, ty)
            x, y = self._next_position(step_move, x, y)
        after = abs(tx - x) + abs(ty - y)
        progress = before - after
        energy_cost = speed * self.rollout_horizon * 0.05
        value = progress * 0.25 - energy_cost - float(state.get("sigma_total", 0.0)) * 0.10
        return {
            "horizon": float(self.rollout_horizon),
            "distance_before": before,
            "distance_after": after,
            "progress": progress,
            "energy_cost": energy_cost,
            "value": value,
        }

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
        next_x, next_y = GRPOPolicy._next_position(move, x, y)

        before = abs(tx - x) + abs(ty - y)
        after = abs(tx - next_x) + abs(ty - next_y)
        return before - after

    @staticmethod
    def _next_position(move: str, x: float, y: float) -> tuple[float, float]:
        if move == "east":
            return x + 1, y
        if move == "west":
            return x - 1, y
        if move == "north":
            return x, y + 1
        if move == "south":
            return x, y - 1
        return x, y

    @staticmethod
    def _greedy_move(x: float, y: float, tx: float, ty: float) -> str:
        dx = tx - x
        dy = ty - y
        if abs(dx) >= abs(dy) and dx > 0:
            return "east"
        if abs(dx) >= abs(dy) and dx < 0:
            return "west"
        if dy > 0:
            return "north"
        if dy < 0:
            return "south"
        return "hold"

    def _softmax(self, scores: list[float]) -> list[float]:
        if not scores:
            return []
        temperature = max(self.temperature, 0.001)
        max_score = max(scores)
        weights = [exp((score - max_score) / temperature) for score in scores]
        total = sum(weights) or 1.0
        return [weight / total for weight in weights]

    def _normalize_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        move = str(candidate.get("move", "hold"))
        speed = float(candidate.get("speed_mps", self.max_speed_mps))
        if move in {"hold", "handoff_payload"}:
            speed = 0.0
        return {
            **candidate,
            "move": move,
            "speed_mps": max(0.0, min(speed, self.max_speed_mps)),
        }

    def _dedupe_candidates(self, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_candidate(candidate)
            candidate_id = self._candidate_id(normalized)
            if candidate_id in seen:
                continue
            seen.add(candidate_id)
            deduped.append(normalized)
        return deduped

    @staticmethod
    def _candidate_id(candidate: dict[str, Any]) -> str:
        return f"{candidate.get('move', 'hold')}@{float(candidate.get('speed_mps', 0.0)):.2f}"

    @staticmethod
    def _needs_elevator_action(state: dict[str, Any]) -> bool:
        return bool(state.get("elevator_required")) or state.get("current_subtask") in {
            "request_elevator",
            "ride_elevator",
        }

    @staticmethod
    def _risk_flags(state: dict[str, Any]) -> list[str]:
        flags: list[str] = []
        if state.get("stum_gate") == "HIGH" or state.get("should_estop"):
            flags.append("uncertainty_halt")
        if float(state.get("battery_pct", 100.0)) <= 15.0:
            flags.append("low_battery")
        if state.get("payload_over_limit") or state.get("payload_mismatch"):
            flags.append("payload_risk")
        if float(state.get("nearest_human_distance_m", 999.0)) < 0.8:
            flags.append("human_nearby")
        fleet_context = state.get("fleet_context", {})
        if isinstance(fleet_context, dict) and fleet_context.get("deadlock_risk"):
            flags.append("deadlock_risk")
        return flags

    @staticmethod
    def _reason(move: str, state: dict[str, Any], breakdown: dict[str, float]) -> str:
        if move == "return_to_dock":
            return "low_battery_return" if float(state.get("battery_pct", 100.0)) <= 15.0 else "dock_bias"
        if move == "hold" and breakdown.get("human_safety", 0.0) > 0.0:
            return "human_safety_hold"
        if move == "hold" and breakdown.get("payload", 0.0) > 0.0:
            return "payload_safety_hold"
        if move == "enter_elevator":
            return "task_aligned_elevator"
        if move == "handoff_payload":
            return "task_aligned_handoff"
        return "max_advantage"
