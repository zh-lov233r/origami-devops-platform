"""
中文：多步 Carry & Go 场景 runner，用于模拟配送或返航过程中逐步出现的异常。
English: Multi-step Carry & Go scenario runner for timeline-style delivery or return faults.
"""

from __future__ import annotations

import re
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

import yaml

from origami.core.pipeline import PIC2Pipeline, PipelineResult
from origami.evaluation.scenario_runner import (
    _audit_records,
    _check_expected_value,
    _extract_actual,
    _list_items,
    _percentile,
    _safety_signal_check,
    _violation_analysis,
)
from origami.persistence.artifact_store import ArtifactStore


DEFAULT_MULTISTEP_SCENARIO_DIR = Path("configs/multistep_scenarios")
DEFAULT_MULTISTEP_REPORT_PATH = Path("artifacts/reports/multistep_scenario_report.json")
DEFAULT_MULTISTEP_ARTIFACT_ROOT = Path("artifacts")
DEFAULT_MULTISTEP_INTERVAL_S = 60.0


def list_multistep_scenarios(
    scenario_dir: Path | str = DEFAULT_MULTISTEP_SCENARIO_DIR,
) -> dict[str, Any]:
    """List multi-step scenario YAML files with compact dashboard metadata."""
    root = Path(scenario_dir)
    if not root.exists():
        return {"available": False, "path": str(root), "count": 0, "scenarios": []}

    scenarios: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    for path in sorted([*root.glob("*.yaml"), *root.glob("*.yml")]):
        try:
            loaded = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            parse_errors.append({"path": str(path), "error": str(exc)})
            continue
        if not isinstance(loaded, dict):
            parse_errors.append({"path": str(path), "error": "Multi-step YAML is not a mapping"})
            continue

        steps = loaded.get("steps", [])
        configured_steps = len(steps) if isinstance(steps, list) else 0
        expanded_steps = _configured_step_count(steps) if isinstance(steps, list) else 0
        scenarios.append(
            {
                "id": _safe_multistep_id(str(loaded.get("id", path.stem))) or path.stem,
                "name": loaded.get("name", path.stem),
                "description": loaded.get("description", ""),
                "tags": loaded.get("tags", []),
                "path": str(path),
                "configured_steps": configured_steps,
                "expanded_steps": expanded_steps,
                "time_step_s": loaded.get("time_step_s", DEFAULT_MULTISTEP_INTERVAL_S),
            }
        )

    payload: dict[str, Any] = {
        "available": not parse_errors,
        "path": str(root),
        "count": len(scenarios),
        "scenarios": scenarios,
    }
    if parse_errors:
        payload["parse_errors"] = parse_errors
    return payload


def run_multistep_suite(
    scenario_dir: Path | str = DEFAULT_MULTISTEP_SCENARIO_DIR,
    report_path: Path | str | None = None,
    artifact_root: Path | str | None = None,
) -> dict[str, Any]:
    """Run all multi-step scenario YAML files in a directory."""
    scenario_path = Path(scenario_dir)
    scenario_files = sorted([*scenario_path.glob("*.yaml"), *scenario_path.glob("*.yml")])
    cases = [_load_multistep_scenario(path) for path in scenario_files]
    scenario_results = [_run_multistep_case(case) for case in cases]
    report = _build_multistep_report(scenario_results)

    if artifact_root is not None:
        _persist_multistep_artifacts(ArtifactStore(artifact_root), report, scenario_results)

    if report_path is not None:
        ArtifactStore(".").write_json(report_path, report)

    return report


def run_default_multistep_suite() -> dict[str, Any]:
    """Run the default multi-step scenario suite and write standard artifacts."""
    return run_multistep_suite(
        DEFAULT_MULTISTEP_SCENARIO_DIR,
        DEFAULT_MULTISTEP_REPORT_PATH,
        artifact_root=DEFAULT_MULTISTEP_ARTIFACT_ROOT,
    )


def run_multistep_scenario_case(
    scenario_id: str,
    scenario_dir: Path | str = DEFAULT_MULTISTEP_SCENARIO_DIR,
) -> dict[str, Any]:
    """Run one multi-step scenario YAML file and return a suite-shaped report."""
    scenario_path = _multistep_case_path(scenario_id, scenario_dir)
    if not scenario_path.exists():
        raise ValueError(f"Multi-step scenario not found: {scenario_path}")

    result = _run_multistep_case(_load_multistep_scenario(scenario_path))
    report = _build_multistep_report([result])
    report["scenario"] = _report_multistep_scenario(result)
    return report


def _multistep_case_path(scenario_id: str, scenario_dir: Path | str) -> Path:
    safe_id = _safe_multistep_id(str(scenario_id))
    if not safe_id:
        raise ValueError("Scenario id is required")
    return Path(scenario_dir) / f"{safe_id}.yaml"


def _safe_multistep_id(raw_id: str) -> str:
    lowered = raw_id.lower().strip().replace(" ", "_")
    cleaned = re.sub(r"[^a-z0-9_-]+", "_", lowered)
    return re.sub(r"_+", "_", cleaned).strip("_-")


def _load_multistep_scenario(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text())
    if not isinstance(loaded, dict):
        raise ValueError(f"Multi-step scenario file must contain a mapping: {path}")

    scenario_id = _safe_multistep_id(str(loaded.get("id", "")))
    if not scenario_id:
        raise ValueError(f"Multi-step scenario must define a valid id: {path}")
    loaded["id"] = scenario_id

    steps = loaded.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"Multi-step scenario must define at least one step: {path}")

    initial = loaded.get("initial_observation", loaded.get("observation"))
    if not isinstance(initial, dict):
        raise ValueError(f"Multi-step scenario must define initial_observation: {path}")

    loaded["path"] = str(path)
    _validate_multistep_scenario(loaded, path)
    return loaded


def _validate_multistep_scenario(case: dict[str, Any], path: Path) -> None:
    for numeric_key in (
        "time_step_s",
        "battery_drain_pct_per_step",
        "battery_drain_pct_per_s",
        "battery_drain_pct_per_min",
    ):
        if numeric_key in case:
            _require_non_negative_number(case[numeric_key], f"{path}:{numeric_key}")

    for index, step in enumerate(case["steps"]):
        if not isinstance(step, dict):
            raise ValueError(f"Multi-step scenario step must be a mapping: {path}[{index}]")
        repeat = step.get("repeat", 1)
        if not isinstance(repeat, int) or repeat < 1:
            raise ValueError(f"Step repeat must be a positive integer: {path}[{index}]")
        for numeric_key in (
            "at_s",
            "interval_s",
            "battery_drain_pct",
            "battery_drain_pct_per_s",
            "battery_drain_pct_per_min",
        ):
            if numeric_key in step:
                _require_non_negative_number(step[numeric_key], f"{path}[{index}].{numeric_key}")
        expected = step.get("expected", {})
        if expected is not None and not isinstance(expected, dict):
            raise ValueError(f"Step expected block must be a mapping: {path}[{index}]")


def _require_non_negative_number(value: Any, location: str) -> None:
    try:
        numeric = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{location} must be numeric") from exc
    if numeric < 0:
        raise ValueError(f"{location} must be non-negative")


def _configured_step_count(steps: list[Any]) -> int:
    total = 0
    for step in steps:
        if isinstance(step, dict) and isinstance(step.get("repeat", 1), int):
            total += max(1, int(step.get("repeat", 1)))
        else:
            total += 1
    return total


def _run_multistep_case(case: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(case["id"])
    pipeline = PIC2Pipeline(run_id=scenario_id)
    current_observation = deepcopy(case.get("initial_observation", case.get("observation", {})))
    previous_action: dict[str, Any] | None = None
    step_results: list[dict[str, Any]] = []
    simulation = _simulation_settings(case)

    for source_index, source_step in enumerate(case["steps"]):
        repeat_total = int(source_step.get("repeat", 1))
        for repeat_index in range(repeat_total):
            step_config = _step_occurrence_config(source_step, source_index, repeat_index, repeat_total)
            observation = _build_step_observation(
                current_observation=current_observation,
                step_config=step_config,
                previous_action=previous_action,
                simulation=simulation,
                is_first_step=not step_results,
            )
            result = pipeline.step(observation)
            step_result = _evaluate_step_result(
                scenario_id=scenario_id,
                step_config=step_config,
                step_index=len(step_results),
                result=result,
            )
            step_results.append(step_result)

            current_observation = observation
            previous_action = result.action

            if bool(case.get("stop_on_failure", False)) and not step_result["passed"]:
                break
        if step_results and bool(case.get("stop_on_failure", False)) and not step_results[-1]["passed"]:
            break

    final_expected = case.get("expected", {})
    final_checks = _evaluate_final_expected(final_expected, step_results[-1]["actual"])
    passed = all(step["passed"] for step in step_results) and all(
        check["passed"] for check in final_checks
    )

    return {
        "id": scenario_id,
        "name": case.get("name", scenario_id),
        "path": case.get("path"),
        "description": case.get("description"),
        "tags": case.get("tags", []),
        "passed": passed,
        "total_steps": len(step_results),
        "configured_steps": len(case["steps"]),
        "passed_steps": sum(1 for step in step_results if step["passed"]),
        "failed_steps": sum(1 for step in step_results if not step["passed"]),
        "final_checks": final_checks,
        "final_actual": step_results[-1]["actual"],
        "steps": step_results,
        "timeline": _scenario_timeline(step_results),
        "latency_ms": _scenario_latency_summary(step_results),
        "event_records": [
            record
            for step in step_results
            for record in step["event_records"]
        ],
        "audit_records": _audit_records(scenario_id, pipeline),
    }


def _simulation_settings(case: dict[str, Any]) -> dict[str, Any]:
    return {
        "advance_position": bool(case.get("advance_position", True)),
        "time_step_s": float(case.get("time_step_s", DEFAULT_MULTISTEP_INTERVAL_S)),
        "battery_drain_pct_per_step": float(case.get("battery_drain_pct_per_step", 0.0)),
        "battery_drain_pct_per_s": _battery_drain_per_second(case),
    }


def _battery_drain_per_second(config: dict[str, Any]) -> float:
    per_second = float(config.get("battery_drain_pct_per_s", 0.0))
    per_minute = float(config.get("battery_drain_pct_per_min", 0.0)) / 60.0
    return per_second + per_minute


def _step_occurrence_config(
    source_step: dict[str, Any],
    source_index: int,
    repeat_index: int,
    repeat_total: int,
) -> dict[str, Any]:
    step_config = deepcopy(source_step)
    base_step = step_config.get("step", source_index)
    base_name = step_config.get("name", f"step-{source_index}")
    step_config["_source_index"] = source_index
    step_config["_repeat_index"] = repeat_index
    step_config["_repeat_total"] = repeat_total

    if repeat_total > 1:
        step_config["step"] = f"{base_step}#{repeat_index + 1}"
        step_config["name"] = f"{base_name} ({repeat_index + 1}/{repeat_total})"
        if "at_s" in source_step and repeat_index:
            interval_s = float(source_step.get("interval_s", DEFAULT_MULTISTEP_INTERVAL_S))
            step_config["at_s"] = float(source_step["at_s"]) + repeat_index * interval_s

    return step_config


def _build_step_observation(
    current_observation: dict[str, Any],
    step_config: dict[str, Any],
    previous_action: dict[str, Any] | None,
    simulation: dict[str, Any],
    is_first_step: bool,
) -> dict[str, Any]:
    observation = deepcopy(current_observation)
    step_advance_position = bool(step_config.get("advance_position", simulation["advance_position"]))
    if step_advance_position and previous_action is not None:
        observation = _advance_observation_position(observation, previous_action)

    previous_elapsed_s = _observation_elapsed_s(current_observation)
    at_s = _resolve_step_elapsed_s(step_config, previous_elapsed_s, simulation, is_first_step)
    elapsed_delta_s = max(0.0, at_s - previous_elapsed_s)
    observation = _apply_battery_drain(observation, step_config, simulation, elapsed_delta_s)

    for key in ("observation", "observation_patch"):
        patch = step_config.get(key)
        if isinstance(patch, dict):
            observation = _deep_merge(observation, patch)

    observation["mission_elapsed_s"] = _clean_number(at_s)

    return observation


def _observation_elapsed_s(observation: dict[str, Any]) -> float:
    try:
        return float(observation.get("mission_elapsed_s", 0.0))
    except (TypeError, ValueError):
        return 0.0


def _resolve_step_elapsed_s(
    step_config: dict[str, Any],
    previous_elapsed_s: float,
    simulation: dict[str, Any],
    is_first_step: bool,
) -> float:
    if "at_s" in step_config:
        return float(step_config["at_s"])
    if is_first_step:
        return previous_elapsed_s
    return previous_elapsed_s + float(step_config.get("interval_s", simulation["time_step_s"]))


def _apply_battery_drain(
    observation: dict[str, Any],
    step_config: dict[str, Any],
    simulation: dict[str, Any],
    elapsed_delta_s: float,
) -> dict[str, Any]:
    if not bool(step_config.get("apply_battery_drain", True)):
        return observation
    if "battery_pct" not in observation:
        return observation

    try:
        current_battery = float(observation["battery_pct"])
    except (TypeError, ValueError):
        return observation

    drain_pct = float(step_config.get("battery_drain_pct", simulation["battery_drain_pct_per_step"]))
    drain_pct += _step_battery_drain_per_second(step_config, simulation) * elapsed_delta_s
    if drain_pct <= 0:
        return observation

    observation["battery_pct"] = _clean_number(max(0.0, current_battery - drain_pct))
    return observation


def _step_battery_drain_per_second(
    step_config: dict[str, Any],
    simulation: dict[str, Any],
) -> float:
    if "battery_drain_pct_per_s" in step_config or "battery_drain_pct_per_min" in step_config:
        return _battery_drain_per_second(step_config)
    return float(simulation["battery_drain_pct_per_s"])


def _evaluate_step_result(
    scenario_id: str,
    step_config: dict[str, Any],
    step_index: int,
    result: PipelineResult,
) -> dict[str, Any]:
    actual = _extract_multistep_actual(result)
    expected = step_config.get("expected", {})
    if not isinstance(expected, dict):
        raise ValueError(f"Step expected block must be a mapping: {scenario_id}[{step_index}]")

    violation_analysis = _violation_analysis(expected, actual)
    checks = _evaluate_multistep_expected(expected, actual)
    safety_signal_check = _safety_signal_check(violation_analysis)
    if safety_signal_check is not None:
        checks.append(safety_signal_check)

    passed = all(check["passed"] for check in checks)
    return {
        "step_index": step_index,
        "step": step_config.get("step", step_index),
        "name": step_config.get("name", f"step-{step_index}"),
        "source_step_index": step_config.get("_source_index", step_index),
        "repeat_index": step_config.get("_repeat_index", 0) + 1,
        "repeat_total": step_config.get("_repeat_total", 1),
        "at_s": actual.get("mission_elapsed_s", step_config.get("at_s")),
        "passed": passed,
        "checks": checks,
        "expected": expected,
        "observation": result.observation,
        "actual": actual,
        "violation_analysis": violation_analysis,
        "latency_ms": {event.module: event.latency_ms for event in result.events},
        "event_records": _multistep_event_records(scenario_id, step_config, step_index, result),
    }


def _extract_multistep_actual(result: PipelineResult) -> dict[str, Any]:
    actual = _extract_actual(result)
    observation = result.observation
    position = observation.get("position")
    target = observation.get("target")
    dock_position = observation.get("dock_position")
    actual.update(
        {
            "position": position,
            "battery_pct": observation.get("battery_pct"),
            "mission_elapsed_s": observation.get("mission_elapsed_s"),
            "current_subtask": observation.get("current_subtask"),
            "distance_to_target": _manhattan_distance(position, target),
            "distance_to_dock": _manhattan_distance(position, dock_position),
        }
    )
    return actual


def _evaluate_multistep_expected(
    expected: dict[str, Any],
    actual: dict[str, Any],
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for key, expected_value in expected.items():
        if key == "notes":
            continue
        checks.append(_check_multistep_expected_value(key, expected_value, actual))
    return checks


def _check_multistep_expected_value(
    key: str,
    expected_value: Any,
    actual: dict[str, Any],
) -> dict[str, Any]:
    actual_key = _MULTISTEP_EXPECTED_TO_ACTUAL.get(key)
    if key.startswith("max_"):
        actual_key = actual_key or key.removeprefix("max_")
        actual_value = actual.get(actual_key)
        passed = actual_value is not None and float(actual_value) <= float(expected_value)
        return _expected_check(key, passed, expected_value, actual_value)
    if key.startswith("min_"):
        actual_key = actual_key or key.removeprefix("min_")
        actual_value = actual.get(actual_key)
        passed = actual_value is not None and float(actual_value) >= float(expected_value)
        return _expected_check(key, passed, expected_value, actual_value)
    if actual_key is None:
        return _check_expected_value(key, expected_value, actual)

    actual_value = actual.get(actual_key)
    passed = actual_value == expected_value
    return _expected_check(key, passed, expected_value, actual_value)


def _expected_check(
    key: str,
    passed: bool,
    expected_value: Any,
    actual_value: Any,
) -> dict[str, Any]:
    return {
        "name": key,
        "passed": passed,
        "expected": expected_value,
        "actual": actual_value,
    }


def _evaluate_final_expected(
    final_expected: Any,
    final_actual: dict[str, Any],
) -> list[dict[str, Any]]:
    if final_expected in (None, {}):
        return []
    if not isinstance(final_expected, dict):
        raise ValueError("Top-level expected block must be a mapping")

    checks = [
        _check_multistep_expected_value(key, expected_value, final_actual)
        for key, expected_value in final_expected.items()
        if key != "notes"
    ]
    safety_signal_check = _safety_signal_check(_violation_analysis(final_expected, final_actual))
    if safety_signal_check is not None:
        checks.append(safety_signal_check)
    return checks


def _multistep_event_records(
    scenario_id: str,
    step_config: dict[str, Any],
    step_index: int,
    result: PipelineResult,
) -> list[dict[str, Any]]:
    return [
        {
            "run_id": result.run_id,
            "scenario_id": scenario_id,
            "scenario_step": step_config.get("step", step_index),
            "step_name": step_config.get("name", f"step-{step_index}"),
            "source_step_index": step_config.get("_source_index", step_index),
            "repeat_index": step_config.get("_repeat_index", 0) + 1,
            "repeat_total": step_config.get("_repeat_total", 1),
            "at_s": result.observation.get("mission_elapsed_s", step_config.get("at_s")),
            "pipeline_step": result.step,
            **event.to_dict(),
        }
        for event in result.events
    ]


def _build_multistep_report(scenario_results: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(scenario_results)
    passed = sum(1 for result in scenario_results if result["passed"])
    failed = total - passed
    total_steps = sum(result["total_steps"] for result in scenario_results)
    failed_steps = sum(result["failed_steps"] for result in scenario_results)
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "suite": "carry_go_multistep",
        "total": total,
        "passed": passed,
        "failed": failed,
        "total_steps": total_steps,
        "failed_steps": failed_steps,
        "pass_rate": passed / total if total else 0.0,
        "step_pass_rate": (total_steps - failed_steps) / total_steps if total_steps else 0.0,
        "quality_gate_passed": failed == 0,
        "summary": _multistep_summary(scenario_results),
        "scenarios": [_report_multistep_scenario(result) for result in scenario_results],
    }


def _multistep_summary(scenario_results: list[dict[str, Any]]) -> dict[str, Any]:
    steps = [
        step
        for scenario in scenario_results
        for step in scenario["steps"]
    ]
    timelines = [scenario["timeline"] for scenario in scenario_results]
    min_battery_values = [
        float(timeline["min_battery_pct"])
        for timeline in timelines
        if timeline.get("min_battery_pct") is not None
    ]
    return {
        "stum_gate_counts": _count_step_actual(steps, "stum_gate"),
        "final_move_counts": _count_step_actual(steps, "final_move"),
        "route_strategy_counts": _count_step_actual(steps, "route_strategy"),
        "violation_counts": _count_step_list_actual(steps, "violations"),
        "violation_status_counts": _count_step_violation_statuses(steps),
        "max_duration_s": max((float(timeline.get("duration_s", 0)) for timeline in timelines), default=0),
        "min_battery_pct": _clean_number(min(min_battery_values)) if min_battery_values else None,
        "distance_traveled_cells": _clean_number(
            sum(float(timeline.get("distance_traveled_cells", 0)) for timeline in timelines)
        ),
        "module_latency_ms": _step_latency_summary(steps),
    }


def _persist_multistep_artifacts(
    store: ArtifactStore,
    report: dict[str, Any],
    scenario_results: list[dict[str, Any]],
) -> dict[str, str]:
    event_records = [
        record
        for scenario in scenario_results
        for record in scenario["event_records"]
    ]
    audit_records = [
        record
        for scenario in scenario_results
        for record in scenario["audit_records"]
    ]

    paths = {
        "markdown_report": store.write_text(
            "reports/multistep_scenario_report.md",
            _markdown_multistep_report(report),
        ),
        "event_log": store.write_jsonl("events/multistep_scenario_events.jsonl", event_records),
        "audit_log": store.write_jsonl("audit/multistep_scenario_audit.jsonl", audit_records),
    }
    report["artifacts"] = {name: str(path) for name, path in paths.items()}
    store.write_json("reports/multistep_scenario_report.json", report)
    return report["artifacts"]


def _report_multistep_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in scenario.items()
        if key not in {"event_records", "audit_records"}
    }


def _markdown_multistep_report(report: dict[str, Any]) -> str:
    lines = [
        "# Carry & Go Multi-Step Scenario Report",
        "",
        f"- Generated at: `{report['generated_at']}`",
        f"- Quality gate: `{'PASS' if report['quality_gate_passed'] else 'FAIL'}`",
        f"- Scenario pass rate: `{report['passed']}/{report['total']} ({report['pass_rate']:.0%})`",
        f"- Step pass rate: `{report['total_steps'] - report['failed_steps']}/"
        f"{report['total_steps']} ({report['step_pass_rate']:.0%})`",
        f"- Max duration: `{report['summary']['max_duration_s']}s`",
        f"- Min battery: `{report['summary']['min_battery_pct']}`",
        "",
        "## Timeline Results",
        "",
        "| Scenario | Step | Result | At s | Position | Battery | Final Move | STUM | Route | SEOM | Violations |",
        "| --- | --- | --- | ---: | --- | ---: | --- | --- | --- | --- | --- |",
    ]
    for scenario in report["scenarios"]:
        for step in scenario["steps"]:
            actual = step["actual"]
            violations = ", ".join(actual.get("violations", [])) or "-"
            result = "PASS" if step["passed"] else "FAIL"
            lines.append(
                "| "
                f"`{scenario['id']}` | `{step['name']}` | `{result}` | "
                f"{actual.get('mission_elapsed_s', '-')} | "
                f"`{actual.get('position')}` | {actual.get('battery_pct', '-')} | "
                f"`{actual.get('final_move')}` | `{actual.get('stum_gate')}` | "
                f"`{actual.get('route_strategy')}` | `{actual.get('seom_passed')}` | "
                f"{violations} |"
            )

    lines.extend(
        [
            "",
            "## Counts",
            "",
            f"- Final moves: `{report['summary']['final_move_counts']}`",
            f"- STUM gates: `{report['summary']['stum_gate_counts']}`",
            f"- Route strategies: `{report['summary']['route_strategy_counts']}`",
            f"- Violations: `{report['summary']['violation_counts']}`",
            f"- Safety signal status: `{report['summary']['violation_status_counts']}`",
            f"- Distance traveled cells: `{report['summary']['distance_traveled_cells']}`",
            "",
        ]
    )
    return "\n".join(lines)


def _scenario_latency_summary(step_results: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    return _step_latency_summary(step_results)


def _step_latency_summary(steps: list[dict[str, Any]]) -> dict[str, dict[str, float]]:
    module_values: dict[str, list[float]] = {}
    for step in steps:
        for module, latency_ms in step["latency_ms"].items():
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


def _count_step_actual(steps: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        value = str(step["actual"].get(key))
        counts[value] = counts.get(value, 0) + 1
    return dict(sorted(counts.items()))


def _count_step_list_actual(steps: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        for item in _list_items(step["actual"].get(key, [])):
            counts[item] = counts.get(item, 0) + 1
    return dict(sorted(counts.items()))


def _count_step_violation_statuses(steps: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for step in steps:
        status = str(step.get("violation_analysis", {}).get("status", "none"))
        counts[status] = counts.get(status, 0) + 1
    return dict(sorted(counts.items()))


def _scenario_timeline(step_results: list[dict[str, Any]]) -> dict[str, Any]:
    elapsed_values = [
        float(step["actual"]["mission_elapsed_s"])
        for step in step_results
        if step["actual"].get("mission_elapsed_s") is not None
    ]
    battery_values = [
        float(step["actual"]["battery_pct"])
        for step in step_results
        if step["actual"].get("battery_pct") is not None
    ]
    positions = [
        step["actual"].get("position")
        for step in step_results
        if isinstance(step["actual"].get("position"), list)
    ]
    return {
        "start_s": _clean_number(min(elapsed_values)) if elapsed_values else None,
        "end_s": _clean_number(max(elapsed_values)) if elapsed_values else None,
        "duration_s": (
            _clean_number(max(elapsed_values) - min(elapsed_values)) if elapsed_values else 0
        ),
        "min_battery_pct": _clean_number(min(battery_values)) if battery_values else None,
        "final_battery_pct": (
            step_results[-1]["actual"].get("battery_pct") if step_results else None
        ),
        "final_position": step_results[-1]["actual"].get("position") if step_results else None,
        "path": positions,
        "distance_traveled_cells": _path_distance(positions),
    }


def _manhattan_distance(origin: Any, destination: Any) -> float | None:
    if not (
        isinstance(origin, list)
        and len(origin) >= 2
        and isinstance(destination, list)
        and len(destination) >= 2
    ):
        return None
    return abs(float(destination[0]) - float(origin[0])) + abs(
        float(destination[1]) - float(origin[1])
    )


def _path_distance(positions: list[Any]) -> int | float:
    total = 0.0
    for previous, current in zip(positions, positions[1:]):
        distance = _manhattan_distance(previous, current)
        if distance is not None:
            total += distance
    return _clean_number(total)


def _advance_observation_position(
    observation: dict[str, Any],
    action: dict[str, Any],
) -> dict[str, Any]:
    position = observation.get("position")
    if not isinstance(position, list) or len(position) < 2:
        return observation

    x, y = float(position[0]), float(position[1])
    move = str(action.get("move", "hold"))
    if move == "return_to_dock":
        dock_position = observation.get("dock_position", [0, 0])
        if isinstance(dock_position, list) and len(dock_position) >= 2:
            move = _greedy_move(x, y, float(dock_position[0]), float(dock_position[1]))

    next_x, next_y = _next_position(move, x, y)
    observation["position"] = [_clean_number(next_x), _clean_number(next_y)]
    return observation


def _next_position(move: str, x: float, y: float) -> tuple[float, float]:
    if move == "east":
        return x + 1, y
    if move == "west":
        return x - 1, y
    if move == "north":
        return x, y + 1
    if move == "south":
        return x, y - 1
    return x, y


def _greedy_move(x: float, y: float, tx: float, ty: float) -> str:
    dx = tx - x
    dy = ty - y
    if abs(dx) >= abs(dy) and dx > 0:
        return "east"
    if abs(dx) >= abs(dy) and dx < 0:
        return "west"
    if dy > 0:
        return "north"
    if dy < 0:
        return "south"
    return "hold"


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = deepcopy(value)
    return merged


def _clean_number(value: float) -> int | float:
    return int(value) if value.is_integer() else value


_MULTISTEP_EXPECTED_TO_ACTUAL = {
    "expected_position": "position",
    "final_position": "position",
    "expected_battery_pct": "battery_pct",
    "final_battery_pct": "battery_pct",
    "max_battery_pct": "battery_pct",
    "min_battery_pct": "battery_pct",
    "expected_mission_elapsed_s": "mission_elapsed_s",
    "final_mission_elapsed_s": "mission_elapsed_s",
    "max_mission_elapsed_s": "mission_elapsed_s",
    "min_mission_elapsed_s": "mission_elapsed_s",
    "max_distance_to_target": "distance_to_target",
    "min_distance_to_target": "distance_to_target",
    "max_distance_to_dock": "distance_to_dock",
    "min_distance_to_dock": "distance_to_dock",
}
