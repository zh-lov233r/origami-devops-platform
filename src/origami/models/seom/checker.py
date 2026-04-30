"""中文：SEOM 基础安全检查器，执行 Carry & Go 规则并对不安全动作做覆盖。

English: Basic SEOM safety checker that evaluates Carry & Go rules and overrides unsafe actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuleResult:
    """Structured result for one SEOM safety rule."""

    passed: bool
    severity: str
    category: str
    score: float
    reason: str
    life_safety: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "severity": self.severity,
            "category": self.category,
            "score": self.score,
            "reason": self.reason,
            "life_safety": self.life_safety,
        }


class SEOMChecker:
    """Rule-based Safety-Embedded Objective Model evaluator."""

    _RULE_METADATA: dict[str, dict[str, Any]] = {
        "R1_uncertainty_halt": {
            "severity": "critical",
            "category": "uncertainty",
            "life_safety": True,
            "reason": "STUM uncertainty or emergency flag requires halt.",
        },
        "C01_person_stop_300mm": {
            "severity": "critical",
            "category": "human_safety",
            "life_safety": True,
            "reason": "Nearest person is inside the 300 mm stop distance.",
        },
        "C02_speed_limit": {
            "severity": "medium",
            "category": "motion",
            "reason": "Commanded speed exceeds the Carry & Go limit.",
        },
        "C03_payload_lock": {
            "severity": "high",
            "category": "payload",
            "reason": "Payload is present but lock confirmation is missing.",
        },
        "C04_door_hold_30s": {
            "severity": "high",
            "category": "access",
            "reason": "Door crossing needs an explicit hold confirmation.",
        },
        "C05_privacy_zone": {
            "severity": "medium",
            "category": "privacy",
            "reason": "Camera is enabled inside a privacy zone.",
        },
        "C06_payload_max_10kg": {
            "severity": "high",
            "category": "payload",
            "reason": "Payload weight exceeds the 10 kg Carry & Go limit.",
        },
        "C07_battery_return_15pct": {
            "severity": "medium",
            "category": "energy",
            "reason": "Battery is below return-to-dock threshold.",
        },
        "C08_route_safe": {
            "severity": "high",
            "category": "route",
            "reason": "Planner route is marked unsafe.",
        },
        "C09_elevator_capacity": {
            "severity": "high",
            "category": "elevator",
            "reason": "Elevator entry lacks capacity or has a fleet conflict.",
        },
        "C10_handoff_auth": {
            "severity": "critical",
            "category": "handoff",
            "life_safety": True,
            "reason": "Payload handoff requires recipient authentication.",
        },
        "C11_payload_amdc_consistency": {
            "severity": "high",
            "category": "payload",
            "reason": "AMDC reported payload-over-limit or payload mismatch.",
        },
        "C12_emergency_stop": {
            "severity": "critical",
            "category": "emergency",
            "life_safety": True,
            "reason": "Emergency stop is active or STUM requested e-stop.",
        },
    }

    _FAIL_SCORES = {
        "critical": 0.0,
        "high": 0.25,
        "medium": 0.55,
        "low": 0.75,
    }

    def __init__(
        self,
        lambda_weight: float = 3.5,
        person_stop_distance_m: float = 0.30,
        max_speed_mps: float = 0.40,
        payload_max_kg: float = 10.0,
        battery_return_pct: float = 15.0,
        elevator_min_capacity: int = 1,
        min_required_score: float = 1.0,
    ) -> None:
        self.lambda_weight = lambda_weight
        self.person_stop_distance_m = person_stop_distance_m
        self.max_speed_mps = max_speed_mps
        self.payload_max_kg = payload_max_kg
        self.battery_return_pct = battery_return_pct
        self.elevator_min_capacity = elevator_min_capacity
        self.min_required_score = min_required_score

    def check(self, action: dict[str, Any]) -> dict[str, Any]:
        checked = dict(action)
        state = action.get("state", {})
        rule_details = self._evaluate_rule_details(checked, state)
        rule_results = {rule_id: result.passed for rule_id, result in rule_details.items()}
        violations = [rule for rule, passed in rule_results.items() if not passed]
        life_safety_violations = [
            rule_id
            for rule_id, result in rule_details.items()
            if not result.passed and result.life_safety
        ]
        operational_violations = [
            rule_id
            for rule_id in violations
            if rule_id not in life_safety_violations
        ]
        overrides = self._apply_overrides(checked, violations, life_safety_violations)
        safety_score = min((result.score for result in rule_details.values()), default=1.0)
        seom_penalty = round(
            self.lambda_weight * max(0.0, self.min_required_score - safety_score),
            6,
        )
        gradient_mask = self._gradient_mask(life_safety_violations, operational_violations)

        checked["seom_passed"] = not violations
        checked["rules_checked"] = list(rule_results.keys())
        checked["rule_results"] = rule_results
        checked["rule_details"] = {
            rule_id: result.to_dict()
            for rule_id, result in rule_details.items()
        }
        checked["violations"] = violations
        checked["life_safety_violations"] = life_safety_violations
        checked["operational_violations"] = operational_violations
        checked["safety_overrides"] = overrides
        checked["safety_score"] = safety_score
        checked["seom_penalty"] = seom_penalty
        checked["gradient_mask"] = gradient_mask
        checked["seom_lambda"] = self.lambda_weight
        checked["requires_human_review"] = bool(
            life_safety_violations or "C10_handoff_auth" in violations
        )
        checked["seom_audit"] = self._audit_record(
            input_action=action,
            output_action=checked,
            rule_details=rule_details,
            violations=violations,
            life_safety_violations=life_safety_violations,
            safety_score=safety_score,
            seom_penalty=seom_penalty,
            gradient_mask=gradient_mask,
        )
        return checked

    def _evaluate_rules(self, action: dict[str, Any], state: dict[str, Any]) -> dict[str, bool]:
        return {
            rule_id: result.passed
            for rule_id, result in self._evaluate_rule_details(action, state).items()
        }

    def _evaluate_rule_details(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
    ) -> dict[str, RuleResult]:
        nearest_human = float(state.get("nearest_human_distance_m", 999.0))
        payload_kg = float(state.get("payload_kg", 0.0))
        battery_pct = float(state.get("battery_pct", 100.0))
        current_zone = state.get("current_zone")
        privacy_zones = set(state.get("privacy_zones", []))
        route_safe = bool(state.get("route_safe", True)) and state.get("route_strategy") != "unsafe"
        fleet_context = state.get("fleet_context", {})

        return {
            "R1_uncertainty_halt": self._result(
                "R1_uncertainty_halt",
                state.get("stum_gate") != "HIGH" and not state.get("should_estop", False),
            ),
            "C01_person_stop_300mm": self._result(
                "C01_person_stop_300mm",
                nearest_human >= self.person_stop_distance_m,
            ),
            "C02_speed_limit": self._result(
                "C02_speed_limit",
                float(action.get("speed_mps", 0.0)) <= self.max_speed_mps,
            ),
            "C03_payload_lock": self._result(
                "C03_payload_lock",
                payload_kg <= 0.0 or bool(state.get("payload_locked", True)),
            ),
            "C04_door_hold_30s": self._result(
                "C04_door_hold_30s",
                not state.get("door_crossing") or bool(state.get("door_hold_confirmed", True)),
            ),
            "C05_privacy_zone": self._result(
                "C05_privacy_zone",
                current_zone not in privacy_zones or not action.get("camera_enabled", True),
            ),
            "C06_payload_max_10kg": self._result(
                "C06_payload_max_10kg",
                payload_kg <= self.payload_max_kg,
            ),
            "C07_battery_return_15pct": self._result(
                "C07_battery_return_15pct",
                battery_pct > self.battery_return_pct or action.get("move") == "return_to_dock",
            ),
            "C08_route_safe": self._result("C08_route_safe", route_safe),
            "C09_elevator_capacity": self._result(
                "C09_elevator_capacity",
                self._elevator_capacity_ok(action, state, fleet_context),
            ),
            "C10_handoff_auth": self._result(
                "C10_handoff_auth",
                self._handoff_auth_ok(action, state),
            ),
            "C11_payload_amdc_consistency": self._result(
                "C11_payload_amdc_consistency",
                not bool(state.get("payload_over_limit", False))
                and not bool(state.get("payload_mismatch", False)),
            ),
            "C12_emergency_stop": self._result(
                "C12_emergency_stop",
                not bool(state.get("emergency_stop_active", False))
                and not bool(state.get("should_estop", False)),
            ),
        }

    def _result(self, rule_id: str, passed: bool) -> RuleResult:
        metadata = self._RULE_METADATA[rule_id]
        severity = str(metadata["severity"])
        score = 1.0 if passed else self._FAIL_SCORES.get(severity, 0.50)
        reason = "ok" if passed else str(metadata["reason"])
        return RuleResult(
            passed=passed,
            severity=severity,
            category=str(metadata["category"]),
            score=score,
            reason=reason,
            life_safety=bool(metadata.get("life_safety", False)),
        )

    def _apply_overrides(
        self,
        checked: dict[str, Any],
        violations: list[str],
        life_safety_violations: list[str],
    ) -> list[str]:
        overrides: list[str] = []

        if "C02_speed_limit" in violations:
            checked["speed_mps"] = self.max_speed_mps
            overrides.append("cap_speed")

        if "C05_privacy_zone" in violations:
            checked["camera_enabled"] = False
            overrides.append("disable_camera")

        if "C07_battery_return_15pct" in violations and not life_safety_violations:
            checked["move"] = "return_to_dock"
            checked["speed_mps"] = min(float(checked.get("speed_mps", self.max_speed_mps)), 0.30)
            overrides.append("return_to_dock")

        if any(
            rule_id in violations
            for rule_id in (
                "C03_payload_lock",
                "C04_door_hold_30s",
                "C06_payload_max_10kg",
                "C08_route_safe",
                "C09_elevator_capacity",
                "C10_handoff_auth",
                "C11_payload_amdc_consistency",
            )
        ):
            checked["move"] = "hold"
            checked["speed_mps"] = 0.0
            overrides.append("hold_for_operational_safety")

        if life_safety_violations:
            checked["move"] = "hold"
            checked["speed_mps"] = 0.0
            if "C12_emergency_stop" in life_safety_violations:
                checked["emergency_stop"] = True
            overrides.append("hold_for_life_safety")

        return self._unique(overrides)

    def _elevator_capacity_ok(
        self,
        action: dict[str, Any],
        state: dict[str, Any],
        fleet_context: Any,
    ) -> bool:
        move = action.get("move")
        current_subtask = state.get("current_subtask")
        needs_elevator = move == "enter_elevator" or current_subtask in {
            "request_elevator",
            "ride_elevator",
        }
        if not needs_elevator:
            return True

        if state.get("elevator_capacity_available") is False:
            return False

        capacity_remaining = int(state.get("elevator_capacity_remaining", self.elevator_min_capacity))
        if capacity_remaining < self.elevator_min_capacity:
            return False

        return not (
            isinstance(fleet_context, dict)
            and (
                fleet_context.get("same_elevator_conflict")
                or fleet_context.get("elevator_queue")
            )
        )

    @staticmethod
    def _handoff_auth_ok(action: dict[str, Any], state: dict[str, Any]) -> bool:
        handoff_moves = {"unlock_payload", "handoff_payload", "deliver_payload"}
        in_handoff = action.get("move") in handoff_moves or state.get("current_subtask") == "handoff_payload"
        if not in_handoff:
            return True
        return bool(state.get("recipient_authenticated", False))

    @staticmethod
    def _gradient_mask(
        life_safety_violations: list[str],
        operational_violations: list[str],
    ) -> str:
        if life_safety_violations:
            return "zero"
        if operational_violations:
            return "reduced"
        return "pass"

    @staticmethod
    def _audit_record(
        input_action: dict[str, Any],
        output_action: dict[str, Any],
        rule_details: dict[str, RuleResult],
        violations: list[str],
        life_safety_violations: list[str],
        safety_score: float,
        seom_penalty: float,
        gradient_mask: str,
    ) -> dict[str, Any]:
        return {
            "policy_version": "seom-carry-go-v0",
            "input_action": SEOMChecker._action_summary(input_action),
            "output_action": SEOMChecker._action_summary(output_action),
            "violations": violations,
            "life_safety_violations": life_safety_violations,
            "safety_score": safety_score,
            "seom_penalty": seom_penalty,
            "gradient_mask": gradient_mask,
            "rule_details": {
                rule_id: result.to_dict()
                for rule_id, result in rule_details.items()
            },
        }

    @staticmethod
    def _action_summary(action: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "move",
            "speed_mps",
            "camera_enabled",
            "emergency_stop",
            "requires_human_review",
        )
        return {
            key: action[key]
            for key in keys
            if key in action
        }

    @staticmethod
    def _unique(items: list[str]) -> list[str]:
        unique_items: list[str] = []
        for item in items:
            if item not in unique_items:
                unique_items.append(item)
        return unique_items
