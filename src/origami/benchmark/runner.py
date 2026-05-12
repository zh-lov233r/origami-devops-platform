"""
中文：延迟 benchmark runner，反复执行 pipeline、汇总模块耗时并生成质量门报告。
English: Latency benchmark runner that repeatedly executes the pipeline, summarizes module timings, and emits quality-gate reports.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from origami.core.pipeline import PIC2Pipeline
from origami.persistence.artifact_store import ArtifactStore
from origami.persistence.run_history import new_run_id, safe_run_id


DEFAULT_BENCHMARK_REPORT_PATH = Path("artifacts/reports/benchmark_report.json")
DEFAULT_BENCHMARK_ARTIFACT_ROOT = Path("artifacts")


def run_latency_benchmark(
    steps: int = 20,
    report_path: Path | str | None = None,
    artifact_root: Path | str | None = None,
    max_module_p95_ms: float = 50.0,
    run_id: str | None = None,
) -> dict[str, object]:
    """Run a deterministic latency benchmark and optionally write a JSON report."""
    resolved_run_id = safe_run_id(run_id) if run_id else new_run_id("benchmark")
    pipeline = PIC2Pipeline(run_id=resolved_run_id)
    module_latencies: dict[str, list[float]] = {}
    event_records: list[dict[str, Any]] = []

    for step in range(steps):
        result = pipeline.step(
            {
                "mission_type": "carry_go_delivery",
                "position": [step, 0],
                "target": [step + 1, 1],
                "sensor_bias": 0.01,
                "payload_kg": 2.0,
                "payload_locked": True,
                "battery_pct": max(20, 90 - step),
                "nearest_human_distance_m": 1.5,
                "fleet_context": {
                    "nearby_robots": step % 3 == 0,
                    "corridor_occupied": step % 7 == 0,
                    "elevator_queue": 0,
                },
            }
        )
        for event in result.events:
            module_latencies.setdefault(event.module, []).append(event.latency_ms)
            event_records.append(
                {
                    "run_id": resolved_run_id,
                    "step": result.step,
                    **event.to_dict(),
                }
            )

    audit_valid = pipeline.audit.verify()[0]
    audit_records = [entry.data for entry in pipeline.audit.entries]
    module_summary = {
        module: _latency_summary(values)
        for module, values in sorted(module_latencies.items())
    }
    quality_gate_passed = audit_valid and all(
        summary["p95"] <= max_module_p95_ms
        for summary in module_summary.values()
    )

    report: dict[str, object] = {
        "run_id": resolved_run_id,
        "generated_at": datetime.now(UTC).isoformat(),
        "steps": steps,
        "thresholds": {"max_module_p95_ms": max_module_p95_ms},
        "avg_latency_ms": {
            module: summary["avg"] for module, summary in module_summary.items()
        },
        "module_latency_ms": module_summary,
        "audit_valid": audit_valid,
        "quality_gate_passed": quality_gate_passed,
    }

    if artifact_root is not None:
        _persist_benchmark_artifacts(
            ArtifactStore(artifact_root),
            report,
            event_records,
            audit_records,
        )

    if report_path is not None:
        ArtifactStore(".").write_json(report_path, report)

    return report


def run_default_latency_benchmark() -> dict[str, object]:
    """Run the default benchmark and write the standard report artifact."""
    return run_latency_benchmark(
        report_path=DEFAULT_BENCHMARK_REPORT_PATH,
        artifact_root=DEFAULT_BENCHMARK_ARTIFACT_ROOT,
    )


def _persist_benchmark_artifacts(
    store: ArtifactStore,
    report: dict[str, object],
    event_records: list[dict[str, Any]],
    audit_records: list[dict[str, Any]],
) -> dict[str, str]:
    run_dir = Path("runs") / str(report["run_id"])
    paths = {
        "json_report": store.write_json(run_dir / "benchmark_report.json", report),
        "event_log": store.write_jsonl(run_dir / "benchmark_events.jsonl", event_records),
        "audit_log": store.write_jsonl(run_dir / "benchmark_audit.jsonl", audit_records),
    }
    latest_paths = {
        "json_report": store.write_json("reports/benchmark_report.json", report),
        "event_log": store.write_jsonl("events/benchmark_events.jsonl", event_records),
        "audit_log": store.write_jsonl("audit/benchmark_audit.jsonl", audit_records),
    }
    report["artifacts"] = {name: str(path) for name, path in paths.items()}
    report["latest_artifacts"] = {name: str(path) for name, path in latest_paths.items()}
    store.write_json(run_dir / "benchmark_report.json", report)
    store.write_json("reports/benchmark_report.json", report)
    return report["artifacts"]


def _latency_summary(values: list[float]) -> dict[str, float]:
    return {
        "avg": round(mean(values), 4),
        "p50": round(median(values), 4),
        "p95": round(_percentile(values, 0.95), 4),
        "max": round(max(values), 4),
    }


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((len(ordered) - 1) * percentile)))
    return ordered[index]
