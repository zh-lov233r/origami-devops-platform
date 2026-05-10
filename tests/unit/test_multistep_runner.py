"""
中文：Multi-step scenario runner 单元测试，验证时间线式配送异常模拟。
English: Unit tests for timeline-style multi-step delivery fault scenarios.
"""

import json
from pathlib import Path
from shutil import copyfile

from origami.evaluation.multistep_runner import (
    run_multistep_scenario_case,
    run_multistep_suite,
)


def test_multistep_runner_executes_low_battery_return_timeline(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "multistep"
    scenario_dir.mkdir()
    copyfile(
        Path("configs/multistep_scenarios") / "delivery_low_battery_return.yaml",
        scenario_dir / "delivery_low_battery_return.yaml",
    )
    report_path = tmp_path / "multistep_report.json"

    report = run_multistep_suite(scenario_dir, report_path, artifact_root=tmp_path)

    assert report["suite"] == "carry_go_multistep"
    assert report["total"] == 1
    assert report["passed"] == 1
    assert report["total_steps"] == 5
    assert report["failed_steps"] == 0
    assert report["quality_gate_passed"] is True
    assert json.loads(report_path.read_text())["quality_gate_passed"] is True
    assert "return_to_dock" in report["summary"]["final_move_counts"]
    assert "seom" in report["summary"]["module_latency_ms"]

    scenario = report["scenarios"][0]
    steps = {step["step"]: step for step in scenario["steps"]}

    assert steps["depart"]["actual"]["final_move"] == "east"
    assert steps["en_route"]["observation"]["position"] == [1, 0]
    assert steps["return_required"]["actual"]["final_move"] == "return_to_dock"
    assert steps["return_required"]["actual"]["route_strategy"] == "safe_halt_or_return"
    assert "battery_abort" in steps["return_required"]["actual"]["replan_reasons"]
    assert "low_battery" in steps["return_required"]["actual"]["grpo_risk_flags"]
    assert steps["returning"]["observation"]["position"] == [2, 0]
    assert scenario["timeline"]["duration_s"] == 240
    assert scenario["timeline"]["final_position"] == [2, 0]
    assert report["summary"]["min_battery_pct"] == 8

    assert "artifacts" in report
    assert (tmp_path / "reports/multistep_scenario_report.md").exists()
    assert (tmp_path / "events/multistep_scenario_events.jsonl").exists()
    assert (tmp_path / "audit/multistep_scenario_audit.jsonl").exists()


def test_multistep_runner_executes_one_case(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "multistep"
    scenario_dir.mkdir()
    copyfile(
        Path("configs/multistep_scenarios") / "delivery_low_battery_return.yaml",
        scenario_dir / "delivery_low_battery_return.yaml",
    )

    report = run_multistep_scenario_case("delivery_low_battery_return", scenario_dir)

    assert report["total"] == 1
    assert report["scenario"]["id"] == "delivery_low_battery_return"
    assert report["scenario"]["passed"] is True
    assert report["scenario"]["final_actual"]["final_move"] == "return_to_dock"


def test_multistep_runner_fails_unexpected_safety_signal(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "multistep"
    scenario_dir.mkdir()
    (scenario_dir / "unexpected_human_timeline.yaml").write_text(
        """
version: 1
id: unexpected_human_timeline
name: Unexpected Human Timeline
initial_observation:
  mission_type: carry_go_delivery
  position: [0, 0]
  target: [2, 0]
  sensor_bias: 0.01
  payload_loaded: true
  payload_kg: 2.0
  payload_locked: true
  battery_pct: 80.0
  nearest_human_distance_m: 2.0
  current_subtask: navigate_to_dropoff
  fleet_context:
    nearby_robots: 0
steps:
  - step: nominal
    expected:
      final_move: east
      seom_passed: true
      audit_valid: true
  - step: human_enters_path
    observation_patch:
      nearest_human_distance_m: 0.2
    expected:
      final_move: hold
      final_speed_mps: 0.0
      seom_passed: false
      audit_valid: true
""".lstrip()
    )

    report = run_multistep_suite(scenario_dir)
    scenario = report["scenarios"][0]
    failing_step = scenario["steps"][1]

    assert report["passed"] == 0
    assert report["failed"] == 1
    assert report["failed_steps"] == 1
    assert report["quality_gate_passed"] is False
    assert failing_step["violation_analysis"]["status"] == "unexpected"
    assert failing_step["violation_analysis"]["unexpected"] == ["C01_person_stop_300mm"]
    assert any(
        check["name"] == "safety_signals" and check["passed"] is False
        for check in failing_step["checks"]
    )


def test_multistep_runner_repeats_steps_and_applies_time_battery_drain(
    tmp_path: Path,
) -> None:
    scenario_dir = tmp_path / "multistep"
    scenario_dir.mkdir()
    (scenario_dir / "long_cruise.yaml").write_text(
        """
version: 1
id: long_cruise
name: Long Cruise
time_step_s: 30
battery_drain_pct_per_step: 1.0
initial_observation:
  mission_type: carry_go_delivery
  position: [0, 0]
  target: [5, 0]
  dock_position: [0, 0]
  sensor_bias: 0.01
  payload_loaded: true
  payload_kg: 2.0
  payload_locked: true
  battery_pct: 20.0
  nearest_human_distance_m: 2.0
  current_subtask: navigate_to_dropoff
  fleet_context:
    nearby_robots: 0
steps:
  - step: cruise
    repeat: 3
    expected:
      final_move: east
      seom_passed: true
      audit_valid: true
      route_strategy: normal
expected:
  final_position: [2, 0]
  final_battery_pct: 17.0
  final_mission_elapsed_s: 60
""".lstrip()
    )

    report = run_multistep_suite(scenario_dir)
    scenario = report["scenarios"][0]

    assert report["quality_gate_passed"] is True
    assert report["total_steps"] == 3
    assert scenario["steps"][0]["step"] == "cruise#1"
    assert scenario["steps"][1]["actual"]["position"] == [1, 0]
    assert scenario["steps"][2]["actual"]["battery_pct"] == 17
    assert scenario["timeline"]["duration_s"] == 60
    assert scenario["timeline"]["distance_traveled_cells"] == 2


def test_multistep_runner_rejects_invalid_repeat(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "multistep"
    scenario_dir.mkdir()
    (scenario_dir / "bad_repeat.yaml").write_text(
        """
version: 1
id: bad_repeat
initial_observation:
  position: [0, 0]
steps:
  - step: broken
    repeat: 0
""".lstrip()
    )

    try:
        run_multistep_suite(scenario_dir)
    except ValueError as exc:
        assert "repeat" in str(exc)
    else:
        raise AssertionError("Expected invalid repeat to raise ValueError")
