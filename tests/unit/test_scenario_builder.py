"""
中文：Scenario Manager 单元测试，验证自定义场景 YAML 可以被安全保存、读取、更新与删除。
English: Unit tests for Scenario Manager ensuring custom scenario YAML can be saved, read, updated, and deleted.
"""

from pathlib import Path

import pytest
import yaml

from origami.evaluation.scenario_builder import (
    delete_scenario,
    get_scenario,
    list_scenarios,
    save_scenario,
    update_scenario,
)


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

    detail = get_scenario("custom_human_stop", scenario_dir=tmp_path)

    assert detail["available"] is True
    assert detail["scenario"]["name"] == "Custom Human Stop"


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


def test_scenario_manager_updates_renames_and_deletes_yaml(tmp_path: Path) -> None:
    save_scenario(
        {
            "id": "custom_case",
            "name": "Custom Case",
            "observation": {"position": [0, 0], "target": [1, 1]},
            "expected": {"final_move": "east"},
        },
        scenario_dir=tmp_path,
    )

    updated = update_scenario(
        "custom_case",
        {
            "id": "renamed_case",
            "name": "Renamed Case",
            "tags": ["custom", "edited"],
            "observation": {"position": [0, 0], "target": [2, 2]},
            "expected": {"final_move": "hold", "seom_passed": False},
        },
        scenario_dir=tmp_path,
    )

    assert updated["updated"] is True
    assert updated["previous_id"] == "custom_case"
    assert updated["scenario"]["id"] == "renamed_case"
    assert not (tmp_path / "custom_case.yaml").exists()
    assert (tmp_path / "renamed_case.yaml").exists()

    loaded = get_scenario("renamed_case", scenario_dir=tmp_path)

    assert loaded["scenario"]["expected"]["final_move"] == "hold"

    deleted = delete_scenario("renamed_case", scenario_dir=tmp_path)

    assert deleted["deleted"] is True
    assert not (tmp_path / "renamed_case.yaml").exists()
