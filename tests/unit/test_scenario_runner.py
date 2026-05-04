"""
中文：Scenario runner 单元测试，验证 Carry & Go 场景套件能生成通过的报告。
English: Unit tests for the scenario runner ensuring the Carry & Go suite produces a passing report.
"""

import json
from pathlib import Path
from shutil import copyfile

from origami.evaluation.scenario_runner import run_scenario_suite


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

    assert report["suite"] == "carry_go"
    assert report["total"] == 8
    assert report["passed"] == 8
    assert report["failed"] == 0
    assert report["pass_rate"] == 1.0
    assert report["quality_gate_passed"] is True
    assert report_path.exists()
    assert json.loads(report_path.read_text())["quality_gate_passed"] is True
    assert report["summary"]["final_move_counts"]["hold"] >= 4
    assert "seom" in report["summary"]["module_latency_ms"]
    assert "artifacts" in report
    assert (tmp_path / "reports/scenario_report.md").exists()
    assert (tmp_path / "events/scenario_events.jsonl").exists()
    assert (tmp_path / "audit/scenario_audit.jsonl").exists()
