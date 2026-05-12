"""
中文：Scenario runner 单元测试，验证 Carry & Go 场景套件能生成通过的报告。
English: Unit tests for the scenario runner ensuring the Carry & Go suite produces a passing report.
"""

import json
from pathlib import Path
from shutil import copyfile

from origami.evaluation.scenario_builder import save_scenario
from origami.evaluation.scenario_runner import run_scenario_case, run_scenario_suite


BUILT_IN_SCENARIOS = [
    "corridor_conflict.yaml",
    "elevator_queue.yaml",
    "human_too_close.yaml",
    "low_battery_return.yaml",
    "normal_delivery.yaml",
    "payload_overweight.yaml",
    "privacy_zone.yaml",
    "sensor_blackout.yaml",
]


def test_scenario_runner_executes_all_carry_go_cases(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    for filename in BUILT_IN_SCENARIOS:
        copyfile(Path("configs/scenarios") / filename, scenario_dir / filename)

    report_path = tmp_path / "scenario_report.json"

    report = run_scenario_suite(scenario_dir, report_path, artifact_root=tmp_path)

    assert report["run_id"].startswith("scenario-")
    assert report["suite"] == "carry_go"
    assert report["total"] == 8
    assert report["passed"] == 8
    assert report["failed"] == 0
    assert report["pass_rate"] == 1.0
    assert report["quality_gate_passed"] is True
    assert report_path.exists()
    assert json.loads(report_path.read_text())["quality_gate_passed"] is True
    assert report["summary"]["final_move_counts"]["hold"] >= 4
    assert report["summary"]["violation_status_counts"]["expected"] >= 1
    assert report["summary"]["violation_status_counts"]["none"] >= 1
    assert "seom" in report["summary"]["module_latency_ms"]
    assert "artifacts" in report
    assert (tmp_path / "reports/scenario_report.md").exists()
    assert "Safety Signals" in (tmp_path / "reports/scenario_report.md").read_text()
    assert (tmp_path / "events/scenario_events.jsonl").exists()
    assert (tmp_path / "audit/scenario_audit.jsonl").exists()
    assert Path(report["artifacts"]["json_report"]).exists()
    assert Path(report["artifacts"]["event_log"]).parent.name == report["run_id"]
    assert json.loads(Path(report["artifacts"]["json_report"]).read_text())["run_id"] == report["run_id"]

    scenarios = {scenario["id"]: scenario for scenario in report["scenarios"]}

    assert scenarios["human_too_close"]["violation_analysis"]["status"] == "expected"
    assert scenarios["normal_delivery"]["violation_analysis"]["status"] == "none"
    assert scenarios["human_too_close"]["violation_analysis"]["unexpected"] == []
    assert scenarios["human_too_close"]["violation_analysis"]["missing"] == []


def test_scenario_runner_executes_one_case(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    copyfile(Path("configs/scenarios") / "normal_delivery.yaml", scenario_dir / "normal_delivery.yaml")

    report = run_scenario_case(
        "normal_delivery",
        scenario_dir,
        artifact_root=tmp_path,
        run_id="targeted-normal-delivery",
    )

    assert report["run_id"] == "targeted-normal-delivery"
    assert report["total"] == 1
    assert report["passed"] == 1
    assert report["quality_gate_passed"] is True
    assert report["scenario"]["id"] == "normal_delivery"
    assert report["scenario"]["actual"]["final_move"] == "east"
    assert report["scenario"]["violation_analysis"]["status"] == "none"
    assert "seom" in report["summary"]["module_latency_ms"]
    assert (tmp_path / "runs/targeted-normal-delivery/scenario_report.json").exists()
    assert "targeted-normal-delivery" in (
        tmp_path / "runs/targeted-normal-delivery/scenario_events.jsonl"
    ).read_text()


def test_scenario_runner_uses_custom_overlay_cases(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    custom_dir = tmp_path / "custom-scenarios"
    scenario_dir.mkdir()
    copyfile(Path("configs/scenarios") / "normal_delivery.yaml", scenario_dir / "normal_delivery.yaml")
    save_scenario(
        {
            "id": "normal_delivery",
            "name": "Custom Normal Delivery",
            "observation": {"position": [0, 0], "target": [2, 0]},
            "expected": {"final_move": "east", "seom_passed": True},
        },
        scenario_dir=custom_dir,
    )
    save_scenario(
        {
            "id": "custom_only",
            "name": "Custom Only",
            "observation": {"position": [0, 0], "target": [1, 0]},
            "expected": {"final_move": "east", "seom_passed": True},
        },
        scenario_dir=custom_dir,
    )

    report = run_scenario_suite(
        scenario_dir,
        artifact_root=tmp_path,
        run_id="overlay-suite",
        overlay_scenario_dir=custom_dir,
    )
    single_report = run_scenario_case(
        "custom_only",
        scenario_dir,
        artifact_root=tmp_path,
        run_id="overlay-single",
        overlay_scenario_dir=custom_dir,
    )
    scenarios = {scenario["id"]: scenario for scenario in report["scenarios"]}

    assert report["quality_gate_passed"] is True
    assert report["total"] == 2
    assert scenarios["normal_delivery"]["name"] == "Custom Normal Delivery"
    assert Path(scenarios["normal_delivery"]["path"]).parent == custom_dir
    assert scenarios["custom_only"]["passed"] is True
    assert single_report["scenario"]["id"] == "custom_only"
    assert Path(single_report["scenario"]["path"]).parent == custom_dir


def test_unexpected_violation_fails_scenario(tmp_path: Path) -> None:
    scenario_dir = tmp_path / "scenarios"
    scenario_dir.mkdir()
    (scenario_dir / "unexpected_human.yaml").write_text(
        """
version: 1
id: unexpected_human
name: Unexpected Human Violation
observation:
  mission_type: carry_go_delivery
  position: [0, 0]
  target: [1, 0]
  sensor_bias: 0.01
  payload_kg: 2.0
  payload_locked: true
  battery_pct: 75.0
  nearest_human_distance_m: 0.2
  fleet_context:
    nearby_robots: 0
expected:
  final_move: hold
  final_speed_mps: 0.0
  seom_passed: false
  audit_valid: true
""".lstrip()
    )

    report = run_scenario_suite(scenario_dir)
    scenario = report["scenarios"][0]

    assert report["passed"] == 0
    assert report["failed"] == 1
    assert report["quality_gate_passed"] is False
    assert scenario["violation_analysis"]["status"] == "unexpected"
    assert scenario["violation_analysis"]["unexpected"] == ["C01_person_stop_300mm"]
    assert any(
        check["name"] == "safety_signals" and check["passed"] is False
        for check in scenario["checks"]
    )
