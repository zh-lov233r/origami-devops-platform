"""
中文：Scenario runner 单元测试，验证 Carry & Go 场景套件能生成通过的报告。
English: Unit tests for the scenario runner ensuring the Carry & Go suite produces a passing report.
"""

import json
from pathlib import Path

from origami.evaluation.scenario_runner import run_scenario_suite


def test_scenario_runner_executes_all_carry_go_cases(tmp_path: Path) -> None:
    report_path = tmp_path / "scenario_report.json"

    report = run_scenario_suite("configs/scenarios", report_path)

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
