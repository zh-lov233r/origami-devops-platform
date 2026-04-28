"""
中文：延迟 benchmark runner，反复执行 pipeline 并汇总各模块平均耗时。
English: Latency benchmark runner that repeatedly executes the pipeline and summarizes per-module average timings.
"""

from __future__ import annotations

from statistics import mean

from origami.core.pipeline import PIC2Pipeline


def run_latency_benchmark(steps: int = 20) -> dict[str, object]:
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

    return {
        "steps": steps,
        "avg_latency_ms": {
            module: round(mean(values), 4) for module, values in module_latencies.items()
        },
        "audit_valid": pipeline.audit.verify()[0],
    }
