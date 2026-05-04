"""
中文：延迟 benchmark runner，反复执行 pipeline、汇总模块耗时并生成质量门报告。
English: Latency benchmark runner that repeatedly executes the pipeline, summarizes module timings, and emits quality-gate reports.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean, median

from origami.core.pipeline import PIC2Pipeline


DEFAULT_BENCHMARK_REPORT_PATH = Path("artifacts/reports/benchmark_report.json")


def run_latency_benchmark(
    steps: int = 20,
    report_path: Path | str | None = None,
    max_module_p95_ms: float = 50.0,
) -> dict[str, object]:
    """Run a deterministic latency benchmark and optionally write a JSON report."""
    pipeline = PIC2Pipeline(run_id="benchmark")
    module_latencies: dict[str, list[float]] = {}

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

    audit_valid = pipeline.audit.verify()[0]
    module_summary = {
        module: _latency_summary(values)
        for module, values in sorted(module_latencies.items())
    }
    quality_gate_passed = audit_valid and all(
        summary["p95"] <= max_module_p95_ms
        for summary in module_summary.values()
    )

    report: dict[str, object] = {
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

    if report_path is not None:
        output_path = Path(report_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, sort_keys=True))

    return report


def run_default_latency_benchmark() -> dict[str, object]:
    """Run the default benchmark and write the standard report artifact."""
    return run_latency_benchmark(report_path=DEFAULT_BENCHMARK_REPORT_PATH)


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
