"""
中文：Run history persistence layer，记录 dashboard 触发的 scenario 和 benchmark 运行历史。
English: Run history persistence layer recording scenario and benchmark runs triggered from the dashboard.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from origami.persistence.artifact_store import ArtifactStore


DEFAULT_HISTORY_INDEX_PATH = Path("history/runs.jsonl")


class RunHistoryStore:
    """Small append-only history index with full report snapshots."""

    def __init__(self, root: Path | str = "artifacts") -> None:
        self.root = Path(root)
        self.store = ArtifactStore(self.root)

    def record(self, run_type: str, report: dict[str, Any]) -> dict[str, Any]:
        """Persist a full report snapshot and append a compact history record."""
        record_id = _record_id(run_type, report)
        snapshot_path = Path("history") / run_type / f"{record_id}.json"
        self.store.write_json(snapshot_path, report)

        record = _summarize_run(
            run_type=run_type,
            record_id=record_id,
            report=report,
            artifact_path=self.root / snapshot_path,
        )
        self.store.append_jsonl(DEFAULT_HISTORY_INDEX_PATH, [record])
        return record

    def list(self, limit: int = 50) -> dict[str, Any]:
        """Return newest history records first."""
        path = self.root / DEFAULT_HISTORY_INDEX_PATH
        if not path.exists():
            return {"available": False, "path": str(path), "count": 0, "records": []}

        records: list[dict[str, Any]] = []
        parse_errors: list[dict[str, Any]] = []
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError as exc:
                parse_errors.append({"line": line_number, "error": exc.msg})
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
            else:
                parse_errors.append({"line": line_number, "error": "JSONL record is not an object"})

        payload: dict[str, Any] = {
            "available": not parse_errors,
            "path": str(path),
            "count": len(records),
            "records": list(reversed(records))[:limit],
        }
        if parse_errors:
            payload["parse_errors"] = parse_errors
        return payload


def _record_id(run_type: str, report: dict[str, Any]) -> str:
    generated_at = str(report.get("generated_at") or datetime.now(UTC).isoformat())
    safe_timestamp = (
        generated_at.replace("+00:00", "Z")
        .replace(":", "")
        .replace(".", "")
        .replace("-", "")
    )
    return f"{run_type}-{safe_timestamp}-{uuid4().hex[:8]}"


def _summarize_run(
    run_type: str,
    record_id: str,
    report: dict[str, Any],
    artifact_path: Path,
) -> dict[str, Any]:
    module_latency = _module_latency(report)
    max_p95_ms = max((float(metrics.get("p95", 0.0)) for metrics in module_latency.values()), default=0.0)

    record: dict[str, Any] = {
        "id": record_id,
        "type": run_type,
        "generated_at": report.get("generated_at"),
        "recorded_at": datetime.now(UTC).isoformat(),
        "quality_gate_passed": bool(report.get("quality_gate_passed")),
        "artifact_path": str(artifact_path),
        "max_module_p95_ms": round(max_p95_ms, 4),
    }

    if run_type == "scenario":
        record.update(_scenario_summary(report))
    elif run_type == "benchmark":
        record.update(_benchmark_summary(report))
    return record


def _module_latency(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    direct_latency = report.get("module_latency_ms")
    if isinstance(direct_latency, dict):
        return direct_latency

    summary = report.get("summary", {})
    summary_latency = summary.get("module_latency_ms") if isinstance(summary, dict) else None
    if isinstance(summary_latency, dict):
        return summary_latency
    return {}


def _scenario_summary(report: dict[str, Any]) -> dict[str, Any]:
    summary = report.get("summary", {})
    violation_counts = summary.get("violation_counts", {}) if isinstance(summary, dict) else {}
    violation_total = sum(int(count) for count in violation_counts.values())
    return {
        "suite": report.get("suite"),
        "total": int(report.get("total", 0)),
        "passed": int(report.get("passed", 0)),
        "failed": int(report.get("failed", 0)),
        "pass_rate": float(report.get("pass_rate", 0.0)),
        "violation_total": violation_total,
    }


def _benchmark_summary(report: dict[str, Any]) -> dict[str, Any]:
    thresholds = report.get("thresholds", {})
    max_threshold = thresholds.get("max_module_p95_ms") if isinstance(thresholds, dict) else None
    return {
        "steps": int(report.get("steps", 0)),
        "audit_valid": bool(report.get("audit_valid")),
        "max_module_p95_threshold_ms": max_threshold,
    }
