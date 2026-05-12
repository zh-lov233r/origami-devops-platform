"""
中文：Run history persistence layer，记录 dashboard 触发的 scenario 和 benchmark 运行历史。
English: Run history persistence layer recording scenario and benchmark runs triggered from the dashboard.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from origami.persistence.artifact_store import ArtifactStore


DEFAULT_HISTORY_INDEX_PATH = Path("history/runs.jsonl")
DEFAULT_RUN_RETENTION_LIMIT = 500


class RunHistoryStore:
    """Small append-only history index with full report snapshots."""

    def __init__(
        self,
        root: Path | str = "artifacts",
        retention_limit: int | None = DEFAULT_RUN_RETENTION_LIMIT,
    ) -> None:
        self.root = Path(root)
        self.store = ArtifactStore(self.root)
        self.retention_limit = retention_limit

    def record(
        self,
        run_type: str,
        report: dict[str, Any],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        """Persist a full report snapshot and append a compact history record."""
        record_id = safe_run_id(run_id or str(report.get("run_id") or "") or _record_id(run_type, report))
        report["run_id"] = record_id
        run_dir = Path("runs") / record_id
        snapshot_path = run_dir / "report.json"

        record = _summarize_run(
            run_type=run_type,
            record_id=record_id,
            report=report,
            artifact_path=self.root / snapshot_path,
            artifact_dir=self.root / run_dir,
        )
        report["history_record"] = record
        self.store.write_json(snapshot_path, report)
        with self.store.lock(DEFAULT_HISTORY_INDEX_PATH):
            path = self.root / DEFAULT_HISTORY_INDEX_PATH
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a") as file:
                file.write(json.dumps(record, sort_keys=True, default=str) + "\n")
            self._apply_retention_locked()
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

    def get(self, record_id: str) -> dict[str, Any]:
        """Return one history record with its full persisted report snapshot."""
        history = self.list(limit=10_000)
        record = next(
            (item for item in history["records"] if item.get("id") == record_id),
            None,
        )
        if record is None:
            return {
                "available": False,
                "id": record_id,
                "record": None,
                "data": None,
                "error": "Run history record not found",
            }

        artifact_path = Path(str(record.get("artifact_path", "")))
        if not artifact_path.exists():
            return {
                "available": False,
                "id": record_id,
                "record": record,
                "data": None,
                "path": str(artifact_path),
                "error": "Run history snapshot not found",
            }

        try:
            snapshot = json.loads(artifact_path.read_text())
        except json.JSONDecodeError as exc:
            return {
                "available": False,
                "id": record_id,
                "record": record,
                "data": None,
                "path": str(artifact_path),
                "error": f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}",
            }

        return {
            "available": True,
            "id": record_id,
            "record": record,
            "data": snapshot,
            "path": str(artifact_path),
        }

    def _apply_retention_locked(self) -> None:
        if self.retention_limit is None or self.retention_limit <= 0:
            return

        records = _read_history_records(self.root / DEFAULT_HISTORY_INDEX_PATH)
        if len(records) <= self.retention_limit:
            return

        keep_records = records[-self.retention_limit :]
        prune_records = records[: -self.retention_limit]
        for record in prune_records:
            _remove_run_artifacts(self.root, record)

        path = self.root / DEFAULT_HISTORY_INDEX_PATH
        lines = [json.dumps(record, sort_keys=True, default=str) for record in keep_records]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(lines) + ("\n" if lines else ""))


def new_run_id(run_type: str, generated_at: str | None = None) -> str:
    """Return a unique, filesystem-safe run id with a readable type prefix."""
    timestamp = generated_at or datetime.now(UTC).isoformat()
    safe_timestamp = (
        timestamp.replace("+00:00", "Z")
        .replace(":", "")
        .replace(".", "")
        .replace("-", "")
    )
    return safe_run_id(f"{run_type}-{safe_timestamp}-{uuid4().hex[:8]}")


def safe_run_id(raw_id: str) -> str:
    """Normalize arbitrary run ids into a path-safe token."""
    cleaned = re.sub(r"[^a-zA-Z0-9_.-]+", "-", raw_id.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip(".-")
    return cleaned or new_run_id("run")


def _record_id(run_type: str, report: dict[str, Any]) -> str:
    generated_at = str(report.get("generated_at") or datetime.now(UTC).isoformat())
    return new_run_id(run_type, generated_at)


def _summarize_run(
    run_type: str,
    record_id: str,
    report: dict[str, Any],
    artifact_path: Path,
    artifact_dir: Path,
) -> dict[str, Any]:
    module_latency = _module_latency(report)
    max_p95_ms = max((float(metrics.get("p95", 0.0)) for metrics in module_latency.values()), default=0.0)

    record: dict[str, Any] = {
        "id": record_id,
        "run_id": record_id,
        "type": run_type,
        "generated_at": report.get("generated_at"),
        "recorded_at": datetime.now(UTC).isoformat(),
        "quality_gate_passed": bool(report.get("quality_gate_passed")),
        "artifact_dir": str(artifact_dir),
        "artifact_path": str(artifact_path),
        "artifacts": report.get("artifacts", {}),
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


def _read_history_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []

    records: list[dict[str, Any]] = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            records.append(parsed)
    return records


def _remove_run_artifacts(root: Path, record: dict[str, Any]) -> None:
    artifact_dir = record.get("artifact_dir")
    if not artifact_dir:
        return

    path = Path(str(artifact_dir))
    try:
        relative = path.resolve().relative_to(root.resolve())
    except ValueError:
        return
    if not relative.parts or relative.parts[0] != "runs":
        return
    shutil.rmtree(path, ignore_errors=True)
