"""
中文：Run history 单元测试，验证运行快照和历史索引可以稳定写入与读取。
English: Unit tests for run history ensuring run snapshots and the history index persist reliably.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from origami.persistence.run_history import RunHistoryStore


def test_run_history_records_scenario_and_benchmark(tmp_path: Path) -> None:
    store = RunHistoryStore(tmp_path)

    scenario_record = store.record(
        "scenario",
        {
            "run_id": "scenario-explicit-run",
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
    assert scenario_record["id"] == "scenario-explicit-run"
    assert Path(scenario_record["artifact_dir"]).name == "scenario-explicit-run"
    assert scenario_record["violation_total"] == 1
    assert benchmark_record["steps"] == 20
    assert Path(scenario_record["artifact_path"]).exists()
    assert Path(benchmark_record["artifact_path"]).exists()

    detail = store.get(scenario_record["id"])

    assert detail["available"] is True
    assert detail["record"]["id"] == scenario_record["id"]
    assert detail["data"]["suite"] == "carry_go"
    assert detail["data"]["run_id"] == "scenario-explicit-run"
    assert detail["data"]["history_record"]["artifact_dir"] == scenario_record["artifact_dir"]
    assert detail["data"]["summary"]["module_latency_ms"]["seom"]["p95"] == 0.02


def test_run_history_detail_reports_missing_record(tmp_path: Path) -> None:
    store = RunHistoryStore(tmp_path)

    detail = store.get("scenario-missing")

    assert detail["available"] is False
    assert detail["record"] is None
    assert detail["data"] is None


def test_run_history_retention_keeps_newest_runs(tmp_path: Path) -> None:
    store = RunHistoryStore(tmp_path, retention_limit=2)

    first = store.record(
        "scenario",
        {
            "run_id": "run-one",
            "generated_at": "2026-05-04T18:00:00+00:00",
            "quality_gate_passed": True,
            "summary": {"module_latency_ms": {}},
        },
    )
    second = store.record(
        "scenario",
        {
            "run_id": "run-two",
            "generated_at": "2026-05-04T18:01:00+00:00",
            "quality_gate_passed": True,
            "summary": {"module_latency_ms": {}},
        },
    )
    third = store.record(
        "benchmark",
        {
            "run_id": "run-three",
            "generated_at": "2026-05-04T18:02:00+00:00",
            "quality_gate_passed": True,
            "steps": 1,
            "audit_valid": True,
            "module_latency_ms": {},
        },
    )

    history = store.list(limit=10)
    index_records = [
        json.loads(line)
        for line in (tmp_path / "history/runs.jsonl").read_text().splitlines()
        if line.strip()
    ]

    assert history["count"] == 2
    assert [record["id"] for record in index_records] == [second["id"], third["id"]]
    assert not Path(first["artifact_dir"]).exists()
    assert Path(second["artifact_dir"]).exists()
    assert Path(third["artifact_dir"]).exists()


def test_run_history_concurrent_records_do_not_corrupt_index(tmp_path: Path) -> None:
    store = RunHistoryStore(tmp_path, retention_limit=None)

    def record(index: int) -> dict:
        return store.record(
            "scenario",
            {
                "run_id": f"concurrent-{index}",
                "generated_at": f"2026-05-04T18:0{index}:00+00:00",
                "quality_gate_passed": True,
                "summary": {"module_latency_ms": {}},
            },
        )

    with ThreadPoolExecutor(max_workers=4) as executor:
        records = list(executor.map(record, range(4)))

    history = store.list(limit=10)

    assert history["available"] is True
    assert history["count"] == 4
    assert {item["id"] for item in history["records"]} == {record["id"] for record in records}
    for record in records:
        assert store.get(record["id"])["available"] is True
