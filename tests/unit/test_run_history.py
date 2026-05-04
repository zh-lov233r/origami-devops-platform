"""
中文：Run history 单元测试，验证运行快照和历史索引可以稳定写入与读取。
English: Unit tests for run history ensuring run snapshots and the history index persist reliably.
"""

from pathlib import Path

from origami.persistence.run_history import RunHistoryStore


def test_run_history_records_scenario_and_benchmark(tmp_path: Path) -> None:
    store = RunHistoryStore(tmp_path)

    scenario_record = store.record(
        "scenario",
        {
            "generated_at": "2026-05-04T18:00:00+00:00",
            "quality_gate_passed": True,
            "suite": "carry_go",
            "total": 8,
            "passed": 8,
            "failed": 0,
            "pass_rate": 1.0,
            "summary": {
                "violation_counts": {"C01_person_stop_300mm": 1},
                "module_latency_ms": {"seom": {"p95": 0.02}},
            },
        },
    )
    benchmark_record = store.record(
        "benchmark",
        {
            "generated_at": "2026-05-04T18:01:00+00:00",
            "quality_gate_passed": True,
            "steps": 20,
            "audit_valid": True,
            "thresholds": {"max_module_p95_ms": 50.0},
            "module_latency_ms": {"grpo": {"p95": 0.03}},
        },
    )

    history = store.list(limit=10)

    assert history["available"] is True
    assert history["count"] == 2
    assert history["records"][0]["id"] == benchmark_record["id"]
    assert history["records"][1]["id"] == scenario_record["id"]
    assert scenario_record["violation_total"] == 1
    assert benchmark_record["steps"] == 20
    assert Path(scenario_record["artifact_path"]).exists()
    assert Path(benchmark_record["artifact_path"]).exists()
