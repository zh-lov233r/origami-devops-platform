"""中文：SEOM 基础安全检查器，执行 Carry & Go 规则并对不安全动作做覆盖。

English: Basic SEOM safety checker that evaluates Carry & Go rules and overrides unsafe actions.
"""

from __future__ import annotations

from typing import Any


class SEOMChecker:
    """Rule-based Safety-Embedded Objective Model evaluator."""

    def __init__(
        self,
        lambda_weight: float = 3.5,
        person_stop_distance_m: float = 0.30,
        max_speed_mps: float = 0.40,
        payload_max_kg: float = 10.0,
        battery_return_pct: float = 15.0,
    ) -> None:
        self.lambda_weight = lambda_weight
        self.person_stop_distance_m = person_stop_distance_m
        self.max_speed_mps = max_speed_mps
        self.payload_max_kg = payload_max_kg
        self.battery_return_pct = battery_return_pct

    def check(self, action: dict[str, Any]) -> dict[str, Any]:
        checked = dict(action)
        state = action.get("state", {})
        rule_results = self._evaluate_rules(checked, state)
        violations = [rule for rule, passed in rule_results.items() if not passed]
        overrides: list[str] = []

        if "R1_uncertainty_halt" in violations or "C01_person_stop_300mm" in violations:
            checked["move"] = "hold"
            checked["speed_mps"] = 0.0
            overrides.append("hold_for_uncertainty_or_person")

        if "C02_speed_limit" in violations:
            checked["speed_mps"] = self.max_speed_mps
            overrides.append("cap_speed")

        if "C05_privacy_zone" in violations:
            checked["camera_enabled"] = False
            overrides.append("disable_camera")

        if "C06_payload_max_10kg" in violations or "C03_payload_lock" in violations:
            checked["move"] = "hold"
            checked["speed_mps"] = 0.0
            overrides.append("hold_for_payload_safety")

        if "C07_battery_return_15pct" in violations:
            checked["move"] = "return_to_dock"
            checked["speed_mps"] = min(float(checked.get("speed_mps", self.max_speed_mps)), 0.30)
            overrides.append("return_to_dock")

        if "C08_route_safe" in violations:
            checked["move"] = "hold"
            checked["speed_mps"] = 0.0
            overrides.append("hold_for_route_safety")

        checked["seom_passed"] = not violations
        checked["rules_checked"] = list(rule_results.keys())
        checked["rule_results"] = rule_results
        checked["violations"] = violations
        checked["safety_overrides"] = overrides
        checked["seom_lambda"] = self.lambda_weight
        return checked

    def _evaluate_rules(self, action: dict[str, Any], state: dict[str, Any]) -> dict[str, bool]:
        nearest_human = float(state.get("nearest_human_distance_m", 999.0))
        payload_kg = float(state.get("payload_kg", 0.0))
        battery_pct = float(state.get("battery_pct", 100.0))
        current_zone = state.get("current_zone")
        privacy_zones = set(state.get("privacy_zones", []))
        route_safe = bool(state.get("route_safe", True)) and state.get("route_strategy") != "unsafe"

        return {
            "R1_uncertainty_halt": state.get("stum_gate") != "HIGH",
            "C01_person_stop_300mm": nearest_human >= self.person_stop_distance_m,
            "C02_speed_limit": float(action.get("speed_mps", 0.0)) <= self.max_speed_mps,
            "C03_payload_lock": payload_kg <= 0.0 or bool(state.get("payload_locked", True)),
            "C04_door_hold_30s": not state.get("door_crossing") or bool(state.get("door_hold_confirmed", True)),
            "C05_privacy_zone": current_zone not in privacy_zones or not action.get("camera_enabled", True),
            "C06_payload_max_10kg": payload_kg <= self.payload_max_kg,
            "C07_battery_return_15pct": battery_pct > self.battery_return_pct
            or action.get("move") == "return_to_dock",
            "C08_route_safe": route_safe,
        }
