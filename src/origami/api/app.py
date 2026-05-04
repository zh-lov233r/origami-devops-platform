"""
中文：FastAPI 控制面应用，提供健康检查、运行接口、报告 API 和 artifact dashboard 页面。
English: FastAPI control-plane app exposing health, run endpoints, report APIs, and the artifact dashboard.
"""

from __future__ import annotations

import json
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from origami.benchmark.runner import DEFAULT_BENCHMARK_REPORT_PATH, run_latency_benchmark
from origami.core.pipeline import PIC2Pipeline
from origami.evaluation.scenario_runner import DEFAULT_REPORT_PATH

app = FastAPI(title="Origami Mini PIC 2.0 DevOps Platform")

ARTIFACT_ROOT = Path("artifacts")
DASHBOARD_STATIC_DIR = Path(__file__).resolve().parents[1] / "dashboard" / "static"

app.mount(
    "/dashboard/static",
    StaticFiles(directory=str(DASHBOARD_STATIC_DIR)),
    name="dashboard-static",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return health()


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD_STATIC_DIR / "dashboard.html")


@app.get("/api/reports/scenario")
def scenario_report() -> dict[str, Any]:
    return _read_json_artifact(DEFAULT_REPORT_PATH)


@app.get("/api/reports/benchmark")
def benchmark_report() -> dict[str, Any]:
    return _read_json_artifact(DEFAULT_BENCHMARK_REPORT_PATH)


@app.get("/api/events/scenario")
def scenario_events(limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    return _read_jsonl_artifact(ARTIFACT_ROOT / "events" / "scenario_events.jsonl", limit)


@app.get("/api/audit/scenario")
def scenario_audit(limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    return _read_jsonl_artifact(ARTIFACT_ROOT / "audit" / "scenario_audit.jsonl", limit)


@app.post("/runs/smoke")
def smoke_run() -> dict[str, object]:
    pipeline = PIC2Pipeline(run_id="api-smoke")
    result = pipeline.step({"position": [0, 0], "target": [1, 1], "sensor_bias": 0.0})
    return result.to_dict()


@app.post("/benchmarks/latency")
def latency_benchmark() -> dict[str, object]:
    return run_latency_benchmark()


def _read_json_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"available": False, "path": str(path), "data": None}

    try:
        return {
            "available": True,
            "path": str(path),
            "data": json.loads(path.read_text()),
        }
    except JSONDecodeError as exc:
        return {
            "available": False,
            "path": str(path),
            "data": None,
            "error": f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}",
        }


def _read_jsonl_artifact(path: Path, limit: int) -> dict[str, Any]:
    if not path.exists():
        return {
            "available": False,
            "path": str(path),
            "count": 0,
            "records": [],
        }

    records: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except JSONDecodeError as exc:
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
        "records": records[-limit:],
    }
    if parse_errors:
        payload["parse_errors"] = parse_errors
    return payload


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
