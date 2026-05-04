"""
中文：Scenario Builder 单元测试，验证自定义场景 YAML 可以被安全保存与列出。
English: Unit tests for Scenario Builder ensuring custom scenario YAML can be safely saved and listed.
"""

from pathlib import Path

import pytest
import yaml

from origami.evaluation.scenario_builder import list_scenarios, save_scenario


def test_scenario_builder_saves_and_lists_custom_yaml(tmp_path: Path) -> None:
    result = save_scenario(
        {
            "id": "Custom Human Stop",
            "name": "Custom Human Stop",
            "description": "Generated in a unit test.",
            "tags": "safety,custom",
            "observation": {
                "position": [0, 0],
                "target": [1, 0],
                "payload_kg": 2.0,
                "payload_locked": True,
                "battery_pct": 80.0,
                "nearest_human_distance_m": 0.2,
                "fleet_context": {"nearby_robots": 0},
            },
            "expected": {
                "final_move": "hold",
                "seom_passed": False,
                "expected_violations": ["C01_person_stop_300mm"],
            },
        },
        scenario_dir=tmp_path,
    )

    scenario_path = Path(result["path"])
    loaded = yaml.safe_load(scenario_path.read_text())
    listed = list_scenarios(tmp_path)

    assert result["scenario"]["id"] == "custom_human_stop"
    assert loaded["id"] == "custom_human_stop"
    assert loaded["observation"]["mission_type"] == "carry_go_delivery"
    assert loaded["expected"]["audit_valid"] is True
    assert listed["count"] == 1
    assert listed["scenarios"][0]["id"] == "custom_human_stop"


def test_scenario_builder_requires_overwrite_for_existing_yaml(tmp_path: Path) -> None:
    payload = {
        "id": "custom_case",
        "name": "Custom Case",
        "observation": {"position": [0, 0], "target": [1, 1]},
        "expected": {"final_move": "east"},
    }

    save_scenario(payload, scenario_dir=tmp_path)

    with pytest.raises(ValueError, match="already exists"):
        save_scenario(payload, scenario_dir=tmp_path)

    overwritten = save_scenario({**payload, "overwrite": True}, scenario_dir=tmp_path)

    assert overwritten["saved"] is True
