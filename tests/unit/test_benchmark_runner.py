"""
中文：Benchmark runner 单元测试，验证延迟报告和质量门字段稳定生成。
English: Unit tests for the benchmark runner ensuring latency reports and quality-gate fields are produced.
"""

import json
from pathlib import Path

from origami.benchmark.runner import run_latency_benchmark


def test_latency_benchmark_writes_quality_report(tmp_path: Path) -> None:
    report_path = tmp_path / "benchmark_report.json"

    report = run_latency_benchmark(
        steps=3,
        report_path=report_path,
        max_module_p95_ms=1000.0,
    )

    assert report["steps"] == 3
    assert report["audit_valid"] is True
    assert report["quality_gate_passed"] is True
    assert "avg_latency_ms" in report
    assert "module_latency_ms" in report
    assert "seom" in report["module_latency_ms"]
    assert report["module_latency_ms"]["seom"]["p95"] >= 0.0
    assert json.loads(report_path.read_text())["quality_gate_passed"] is True
