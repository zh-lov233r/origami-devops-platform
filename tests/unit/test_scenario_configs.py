"""
中文：场景配置单元测试，验证 Carry & Go YAML 场景具备基础 schema。
English: Unit tests for Carry & Go YAML scenario configs and their basic schema.
"""

from pathlib import Path
from typing import Any

import yaml


SCENARIO_DIR = Path("configs/scenarios")
EXPECTED_IDS = {
    "normal_delivery",
    "human_too_close",
    "low_battery_return",
    "payload_overweight",
    "sensor_blackout",
    "elevator_queue",
    "corridor_conflict",
    "privacy_zone",
    "payload_unlocked",
    "door_crossing_without_hold",
    "unsafe_route_marked",
    "handoff_without_auth",
    "emergency_stop_active",
    "corridor_priority_claim",
    "dock_queue_on_low_battery",
    "medium_uncertainty_caution",
    "stale_sensor_replan",
    "camera_depth_drift",
    "floor_friction_low_mu",
    "door_crossing_with_hold_confirmed",
}


def test_carry_go_scenario_configs_have_basic_schema() -> None:
    scenario_paths = sorted(SCENARIO_DIR.glob("*.yaml"))
    scenarios = [_load_yaml(path) for path in scenario_paths]

    assert EXPECTED_IDS <= {scenario["id"] for scenario in scenarios}
    for scenario in scenarios:
        assert scenario["version"] == 1
        assert isinstance(scenario["name"], str)
        assert isinstance(scenario["description"], str)
        assert isinstance(scenario["tags"], list)
        assert isinstance(scenario["observation"], dict)
        assert isinstance(scenario["expected"], dict)
        assert "mission_type" in scenario["observation"]
        assert "final_move" in scenario["expected"]
        assert scenario["expected"].get("audit_valid") is True


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text())
    assert isinstance(loaded, dict)
    return loaded
