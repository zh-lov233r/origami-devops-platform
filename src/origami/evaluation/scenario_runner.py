"""
中文：Carry & Go 场景 runner，读取 YAML 场景、执行 pipeline、校验预期并生成报告。
English: Carry & Go scenario runner that loads YAML cases, runs the pipeline, checks expectations, and writes reports.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

import yaml

from origami.core.pipeline import PIC2Pipeline, PipelineResult


DEFAULT_SCENARIO_DIR = Path("configs/scenarios")
DEFAULT_REPORT_PATH = Path("artifacts/reports/scenario_report.json")


def run_scenario_suite(
    scenario_dir: Path | str = DEFAULT_SCENARIO_DIR,
    report_path: Path | str | None = None,
) -> dict[str, Any]:
    """Run all scenario YAML files in a directory and optionally persist a JSON report."""
    scenario_path = Path(scenario_dir)
    cases = [_load_scenario(path) for path in sorted(scenario_path.glob("*.yaml"))]
    scenario_results = [_run_case(case) for case in cases]
    report = _build_report(scenario_results)

    if report_path is not None:
        output_path = Path(report_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True))

    return report


def run_default_scenario_suite() -> dict[str, Any]:
    """Run the default Carry & Go scenario suite and write the standard report artifact."""
    return run_scenario_suite(DEFAULT_SCENARIO_DIR, DEFAULT_REPORT_PATH)


def _load_scenario(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text())
    if not isinstance(loaded, dict):
        raise ValueError(f"Scenario file must contain a mapping: {path}")
    loaded["path"] = str(path)
    return loaded


def _run_case(case: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(case["id"])
    pipeline = PIC2Pipeline(run_id=scenario_id)
    result = pipeline.step(case["observation"])
    actual = _extract_actual(result)
    checks = _evaluate_expected(case.get("expected", {}), actual)
    passed = all(check["passed"] for check in checks)
    return {
        "id": scenario_id,
        "name": case.get("name", scenario_id),
        "path": case.get("path"),
        "tags": case.get("tags", []),
        "passed": passed,
        "checks": checks,
        "actual": actual,
        "latency_ms": {event.module: event.latency_ms for event in result.events},
    }


def _extract_actual(result: PipelineResult) -> dict[str, Any]:
    action = result.action
    state = action.get("state", {})
    grpo = action.get("grpo", {})
    crl_mrs = action.get("crl_mrs", {})
    reservation = action.get("reservation_request", {})
    return {
        "final_move": action.get("move"),
        "final_speed_mps": action.get("speed_mps"),
        "camera_enabled": action.get("camera_enabled"),
        "seom_passed": action.get("seom_passed"),
        "violations": action.get("violations", []),
        "life_safety_violations": action.get("life_safety_violations", []),
        "gradient_mask": action.get("gradient_mask"),
        "requires_human_review": action.get("requires_human_review"),
        "audit_valid": result.audit_valid,
        "stum_gate": state.get("stum_gate"),
        "autonomy_mode": state.get("autonomy_mode"),
        "route_strategy": state.get("route_strategy"),
        "replan_reasons": state.get("replan_reasons", []),
        "recovery_actions": state.get("recovery_actions", []),
        "grpo_selected_reason": grpo.get("selected_reason"),
        "grpo_risk_flags": grpo.get("risk_flags", []),
        "fleet_adjustment": action.get("fleet_adjustment"),
        "conflict_events": crl_mrs.get("conflict_events", []),
        "cooperation_events": crl_mrs.get("cooperation_events", []),
        "resource": reservation.get("resource"),
        "reservation_status": reservation.get("status"),
    }


def _evaluate_expected(expected: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for key, expected_value in expected.items():
        if key == "notes":
            continue
        check = _check_expected_value(key, expected_value, actual)
        checks.append(check)
    return checks


def _check_expected_value(
    key: str,
    expected_value: Any,
    actual: dict[str, Any],
) -> dict[str, Any]:
    actual_key = _EXPECTED_TO_ACTUAL.get(key, key)
    actual_value = actual.get(actual_key)

    if key.startswith("expected_") and key.endswith("_any_of"):
        if isinstance(actual_value, list):
            passed = any(item in actual_value for item in expected_value)
        else:
            passed = actual_value in expected_value
    elif key.endswith("_any_of"):
        passed = actual_value in expected_value
    elif key.startswith("expected_") or key.startswith("required_"):
        passed = _check_list_expectation(key, expected_value, actual_value)
    elif key.startswith("max_"):
        passed = actual_value is not None and float(actual_value) <= float(expected_value)
    else:
        passed = actual_value == expected_value

    return {
        "name": key,
        "passed": passed,
        "expected": expected_value,
        "actual": actual_value,
    }


def _check_list_expectation(key: str, expected_value: Any, actual_value: Any) -> bool:
    expected_items = expected_value if isinstance(expected_value, list) else [expected_value]

    if key.startswith("required_absent_"):
        actual_items = actual_value if isinstance(actual_value, list) else [actual_value]
        return all(item not in actual_items for item in expected_items)
    if not isinstance(actual_value, list):
        return actual_value == expected_value

    actual_items = actual_value
    return all(item in actual_items for item in expected_items)


def _build_report(scenario_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(scenario_results)
    passed = sum(1 for result in scenario_results if result["passed"])
    failed = total - passed
    latencies = _latency_summary(scenario_results)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "suite": "carry_go",
        "total": total,
        "passed": passed,
        "failed": failed,
        "pass_rate": passed / total if total else 0.0,
        "quality_gate_passed": failed == 0,
        "summary": {
            "stum_gate_counts": _count_actual(scenario_results, "stum_gate"),
            "final_move_counts": _count_actual(scenario_results, "final_move"),
            "fleet_adjustment_counts": _count_actual(scenario_results, "fleet_adjustment"),
            "violation_counts": _count_list_actual(scenario_results, "violations"),
            "module_latency_ms": latencies,
        },
        "scenarios": scenario_results,
    }


def _latency_summary(scenario_results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    module_values: dict[str, list[float]] = {}
    for scenario in scenario_results:
        for module, latency_ms in scenario["latency_ms"].items():
            module_values.setdefault(module, []).append(float(latency_ms))

    return {
        module: {
            "avg": round(mean(values), 4),
            "p50": round(median(values), 4),
            "p95": round(_percentile(values, 0.95), 4),
            "max": round(max(values), 4),
        }
        for module, values in sorted(module_values.items())
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _count_actual(scenario_results: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter = Counter(str(result["actual"].get(key)) for result in scenario_results)
    return dict(sorted(counter.items()))


def _count_list_actual(scenario_results: list[dict[str, Any]], key: str) -> dict[str, int]:
    counter: Counter[str] = Counter()
    for result in scenario_results:
        for item in result["actual"].get(key, []):
            counter[str(item)] += 1
    return dict(sorted(counter.items()))


_EXPECTED_TO_ACTUAL = {
    "max_final_speed_mps": "final_speed_mps",
    "stum_gate_any_of": "stum_gate",
    "expected_violations": "violations",
    "required_absent_violations": "violations",
    "expected_life_safety_violations": "life_safety_violations",
    "expected_replan_reasons": "replan_reasons",
    "expected_recovery_actions": "recovery_actions",
    "expected_grpo_risk_flags": "grpo_risk_flags",
    "expected_fleet_adjustment": "fleet_adjustment",
    "expected_fleet_adjustment_any_of": "fleet_adjustment",
    "expected_conflict_events": "conflict_events",
    "expected_conflict_events_any_of": "conflict_events",
    "expected_resource": "resource",
}
