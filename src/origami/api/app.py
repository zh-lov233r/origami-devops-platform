"""
中文：FastAPI 控制面应用，提供健康检查、运行接口、报告 API 和 artifact dashboard 页面。
English: FastAPI control-plane app exposing health, run endpoints, report APIs, and the artifact dashboard.
"""

from __future__ import annotations

import logging
import json
import secrets
from datetime import UTC, datetime
from json import JSONDecodeError
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware

from origami.benchmark.runner import (
    run_latency_benchmark,
)
from origami.core.pipeline import PIC2Pipeline
from origami.core.settings import OrigamiSettings, load_settings
from origami.evaluation.multistep_runner import (
    DEFAULT_MULTISTEP_SCENARIO_DIR,
    DEFAULT_MULTISTEP_REPORT_PATH,
    list_multistep_scenarios,
    run_multistep_scenario_case,
    run_multistep_suite,
)
from origami.evaluation.scenario_builder import (
    delete_scenario,
    get_scenario,
    list_scenarios,
    save_scenario,
    update_scenario,
)
from origami.evaluation.scenario_runner import (
    DEFAULT_REPORT_PATH,
    DEFAULT_SCENARIO_DIR,
    run_scenario_case,
    run_scenario_suite,
)
from origami.observability.metrics import (
    PROMETHEUS_CONTENT_TYPE,
    record_benchmark_report,
    record_http_request,
    record_scenario_report,
    render_metrics,
)
from origami.persistence.run_history import RunHistoryStore

app = FastAPI(title="Origami Mini PIC 2.0 DevOps Platform")

SETTINGS = load_settings()
ARTIFACT_ROOT = SETTINGS.artifact_root
CUSTOM_SCENARIO_DIR = SETTINGS.scenario_config_dir
DASHBOARD_STATIC_DIR = Path(__file__).resolve().parents[1] / "dashboard" / "static"
RUN_HISTORY = RunHistoryStore(ARTIFACT_ROOT, retention_limit=SETTINGS.run_retention_limit)
LOGGER = logging.getLogger("origami.api")
logging.basicConfig(level=getattr(logging, SETTINGS.log_level, logging.INFO))

if SETTINGS.trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(SETTINGS.trusted_hosts))

if SETTINGS.allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(SETTINGS.allowed_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=sorted(
            {
                "Authorization",
                "Content-Type",
                "X-Origami-Actor",
                "X-Origami-Token",
                "X-Request-ID",
                SETTINGS.actor_header,
            }
        ),
        expose_headers=["X-Request-ID"],
    )

app.mount(
    "/dashboard/static",
    StaticFiles(directory=str(DASHBOARD_STATIC_DIR)),
    name="dashboard-static",
)


@app.middleware("http")
async def enforce_auth_and_record_metrics(request: Request, call_next: Any) -> Response:
    request.state.request_id = _request_id(request)
    request.state.actor = _request_actor(request, SETTINGS)
    request.state.source_ip = _source_ip(request)
    started_at = perf_counter()
    status_code = 500
    try:
        auth_response = _auth_error_response(request)
        if auth_response is not None:
            status_code = auth_response.status_code
            auth_response.headers["X-Request-ID"] = request.state.request_id
            if _is_critical_operation(request):
                _log_operation(request, "auth_rejected", status_code=status_code)
            return auth_response

        response: Response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Request-ID"] = request.state.request_id
        if request.url.path == "/dashboard" or request.url.path.startswith("/dashboard/static/"):
            response.headers["Cache-Control"] = "no-store"
        return response
    finally:
        route_path = _route_path(request)
        elapsed = perf_counter() - started_at
        record_http_request(request.method, route_path, status_code, elapsed)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return health()


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return Response(render_metrics(), media_type=PROMETHEUS_CONTENT_TYPE)


@app.get("/api/runtime-config")
def runtime_config() -> dict[str, Any]:
    settings = load_settings()
    return {
        "environment": settings.environment,
        "auth_required": settings.auth_required,
        "metrics_auth_required": settings.metrics_auth_required,
        "artifact_root": str(settings.artifact_root),
        "scenario_config_dir": str(settings.scenario_config_dir),
        "grafana_url": settings.grafana_url,
        "actor_header": settings.actor_header,
        "run_retention_limit": settings.run_retention_limit,
    }


@app.get("/dashboard", include_in_schema=False)
def dashboard() -> FileResponse:
    return FileResponse(DASHBOARD_STATIC_DIR / "dashboard.html")


@app.get("/api/reports/scenario")
def scenario_report() -> dict[str, Any]:
    return _read_json_artifact(_artifact_path(DEFAULT_REPORT_PATH))


@app.get("/api/reports/multistep-scenario")
def multistep_scenario_report() -> dict[str, Any]:
    return _read_json_artifact(_artifact_path(DEFAULT_MULTISTEP_REPORT_PATH))


@app.get("/api/reports/benchmark")
def benchmark_report() -> dict[str, Any]:
    return _read_json_artifact(ARTIFACT_ROOT / "reports" / "benchmark_report.json")


@app.get("/api/events/scenario")
def scenario_events(limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    return _read_jsonl_artifact(ARTIFACT_ROOT / "events" / "scenario_events.jsonl", limit)


@app.get("/api/events/multistep-scenario")
def multistep_scenario_events(limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    return _read_jsonl_artifact(
        ARTIFACT_ROOT / "events" / "multistep_scenario_events.jsonl",
        limit,
    )


@app.get("/api/audit/scenario")
def scenario_audit(limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    return _read_jsonl_artifact(ARTIFACT_ROOT / "audit" / "scenario_audit.jsonl", limit)


@app.get("/api/audit/multistep-scenario")
def multistep_scenario_audit(limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    return _read_jsonl_artifact(
        ARTIFACT_ROOT / "audit" / "multistep_scenario_audit.jsonl",
        limit,
    )


@app.get("/api/history/runs")
def run_history(limit: int = Query(50, ge=1, le=500)) -> dict[str, Any]:
    return RUN_HISTORY.list(limit)


@app.get("/api/history/runs/{record_id}")
def run_history_detail(record_id: str) -> dict[str, Any]:
    payload = RUN_HISTORY.get(record_id)
    if not payload["available"] and payload.get("record") is None:
        raise HTTPException(status_code=404, detail=payload["error"])
    return payload


@app.get("/api/scenarios")
def scenario_configs() -> dict[str, Any]:
    return list_scenarios(DEFAULT_SCENARIO_DIR, overlay_scenario_dir=CUSTOM_SCENARIO_DIR)


@app.get("/api/multistep-scenarios")
def multistep_scenario_configs() -> dict[str, Any]:
    return list_multistep_scenarios()


@app.get("/api/scenarios/{scenario_id}")
def scenario_detail(scenario_id: str) -> dict[str, Any]:
    try:
        return get_scenario(scenario_id, overlay_scenario_dir=CUSTOM_SCENARIO_DIR)
    except ValueError as exc:
        raise _scenario_http_error(exc) from exc


@app.post("/api/scenarios")
def scenario_create(payload: dict[str, Any], request: Request = None) -> dict[str, Any]:
    try:
        result = save_scenario(payload, scenario_dir=CUSTOM_SCENARIO_DIR)
        _log_operation(
            request,
            "scenario_create",
            status_code=200,
            target=result.get("scenario", {}).get("id"),
            metadata={"path": result.get("path")},
        )
        return result
    except ValueError as exc:
        _log_operation(request, "scenario_create_failed", status_code=400, metadata={"error": str(exc)})
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.put("/api/scenarios/{scenario_id}")
def scenario_update(
    scenario_id: str,
    payload: dict[str, Any],
    request: Request = None,
) -> dict[str, Any]:
    try:
        result = update_scenario(
            scenario_id,
            payload,
            scenario_dir=CUSTOM_SCENARIO_DIR,
            create_if_missing=True,
        )
        _log_operation(
            request,
            "scenario_update",
            status_code=200,
            target=result.get("scenario", {}).get("id", scenario_id),
            metadata={
                "previous_id": result.get("previous_id"),
                "path": result.get("path"),
            },
        )
        return result
    except ValueError as exc:
        _log_operation(
            request,
            "scenario_update_failed",
            status_code=400,
            target=scenario_id,
            metadata={"error": str(exc)},
        )
        raise _scenario_http_error(exc) from exc


@app.delete("/api/scenarios/{scenario_id}")
def scenario_delete(scenario_id: str, request: Request = None) -> dict[str, Any]:
    try:
        result = delete_scenario(scenario_id, scenario_dir=CUSTOM_SCENARIO_DIR)
        _log_operation(
            request,
            "scenario_delete",
            status_code=200,
            target=result.get("id", scenario_id),
            metadata={"path": result.get("path")},
        )
        return result
    except ValueError as exc:
        _log_operation(
            request,
            "scenario_delete_failed",
            status_code=400,
            target=scenario_id,
            metadata={"error": str(exc)},
        )
        raise _scenario_http_error(exc) from exc


@app.post("/runs/smoke")
def smoke_run(request: Request = None) -> dict[str, object]:
    pipeline = PIC2Pipeline(run_id="api-smoke")
    result = pipeline.step({"position": [0, 0], "target": [1, 1], "sensor_bias": 0.0})
    payload = result.to_dict()
    _log_operation(request, "run_smoke", status_code=200, run_id=str(payload.get("run_id")))
    return payload


@app.post("/runs/scenario")
def scenario_run(request: Request = None) -> dict[str, Any]:
    report = run_scenario_suite(
        DEFAULT_SCENARIO_DIR,
        ARTIFACT_ROOT / "reports" / "scenario_report.json",
        artifact_root=ARTIFACT_ROOT,
        overlay_scenario_dir=CUSTOM_SCENARIO_DIR,
    )
    report["history_record"] = RUN_HISTORY.record("scenario", report, run_id=str(report["run_id"]))
    record_scenario_report(report, scope="suite")
    _log_operation(
        request,
        "run_scenario_suite",
        status_code=200,
        run_id=report["history_record"].get("id"),
        metadata={
            "quality_gate_passed": report.get("quality_gate_passed"),
            "total": report.get("total"),
            "failed": report.get("failed"),
        },
    )
    return report


@app.post("/runs/scenario/{scenario_id}")
def scenario_run_one(scenario_id: str, request: Request = None) -> dict[str, Any]:
    try:
        report = run_scenario_case(
            scenario_id,
            artifact_root=ARTIFACT_ROOT,
            overlay_scenario_dir=CUSTOM_SCENARIO_DIR,
        )
        report["history_record"] = RUN_HISTORY.record("scenario", report, run_id=str(report["run_id"]))
        record_scenario_report(report, scope=report.get("scenario", {}).get("id", scenario_id))
        _log_operation(
            request,
            "run_scenario",
            status_code=200,
            target=scenario_id,
            run_id=report["history_record"].get("id"),
            metadata={"quality_gate_passed": report.get("quality_gate_passed")},
        )
        return report
    except ValueError as exc:
        _log_operation(
            request,
            "run_scenario_failed",
            status_code=400,
            target=scenario_id,
            metadata={"error": str(exc)},
        )
        raise _scenario_http_error(exc) from exc


@app.post("/runs/multistep-scenario")
def multistep_scenario_run(request: Request = None) -> dict[str, Any]:
    report = run_multistep_suite(
        DEFAULT_MULTISTEP_SCENARIO_DIR,
        ARTIFACT_ROOT / "reports" / "multistep_scenario_report.json",
        artifact_root=ARTIFACT_ROOT,
    )
    report["history_record"] = RUN_HISTORY.record("scenario", report, run_id=str(report["run_id"]))
    record_scenario_report(report, scope="multistep-suite")
    _log_operation(
        request,
        "run_multistep_scenario_suite",
        status_code=200,
        run_id=report["history_record"].get("id"),
        metadata={
            "quality_gate_passed": report.get("quality_gate_passed"),
            "total": report.get("total"),
            "failed": report.get("failed"),
        },
    )
    return report


@app.post("/runs/multistep-scenario/{scenario_id}")
def multistep_scenario_run_one(
    scenario_id: str,
    request: Request = None,
) -> dict[str, Any]:
    try:
        report = run_multistep_scenario_case(scenario_id, artifact_root=ARTIFACT_ROOT)
        scope = report.get("scenario", {}).get("id", scenario_id)
        report["history_record"] = RUN_HISTORY.record("scenario", report, run_id=str(report["run_id"]))
        record_scenario_report(report, scope=f"multistep-{scope}")
        _log_operation(
            request,
            "run_multistep_scenario",
            status_code=200,
            target=scenario_id,
            run_id=report["history_record"].get("id"),
            metadata={"quality_gate_passed": report.get("quality_gate_passed")},
        )
        return report
    except ValueError as exc:
        _log_operation(
            request,
            "run_multistep_scenario_failed",
            status_code=400,
            target=scenario_id,
            metadata={"error": str(exc)},
        )
        raise _scenario_http_error(exc) from exc


@app.post("/runs/benchmark")
def benchmark_run(request: Request = None) -> dict[str, object]:
    report = run_latency_benchmark(
        report_path=ARTIFACT_ROOT / "reports" / "benchmark_report.json",
        artifact_root=ARTIFACT_ROOT,
    )
    report["history_record"] = RUN_HISTORY.record("benchmark", report, run_id=str(report["run_id"]))
    record_benchmark_report(report)
    _log_operation(
        request,
        "run_benchmark",
        status_code=200,
        run_id=report["history_record"].get("id"),
        metadata={
            "quality_gate_passed": report.get("quality_gate_passed"),
            "audit_valid": report.get("audit_valid"),
        },
    )
    return report


@app.post("/benchmarks/latency")
def latency_benchmark(request: Request = None) -> dict[str, object]:
    report = run_latency_benchmark(artifact_root=ARTIFACT_ROOT)
    report["history_record"] = RUN_HISTORY.record("benchmark", report, run_id=str(report["run_id"]))
    record_benchmark_report(report)
    _log_operation(
        request,
        "run_latency_benchmark",
        status_code=200,
        run_id=report["history_record"].get("id"),
        metadata={
            "quality_gate_passed": report.get("quality_gate_passed"),
            "audit_valid": report.get("audit_valid"),
        },
    )
    return report


def _route_path(request: Any) -> str:
    route = request.scope.get("route")
    return str(getattr(route, "path", request.url.path))


def _request_id(request: Request) -> str:
    supplied = request.headers.get("x-request-id", "").strip()
    return supplied or uuid4().hex


def _request_actor(request: Request, settings: OrigamiSettings) -> str:
    actor = request.headers.get(settings.actor_header, "").strip()
    if actor:
        return actor
    if _request_token(request):
        return "token-authenticated"
    return "anonymous"


def _source_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for", "").split(",", maxsplit=1)[0].strip()
    if forwarded_for:
        return forwarded_for
    return request.client.host if request.client else "unknown"


def _is_critical_operation(request: Request) -> bool:
    path = request.url.path
    if request.method in {"POST", "PUT", "DELETE"} and (
        path.startswith("/runs")
        or path.startswith("/benchmarks")
        or path.startswith("/api/scenarios")
    ):
        return True
    return False


def _log_operation(
    request: Request | None,
    action: str,
    *,
    status_code: int,
    target: str | None = None,
    run_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    if request is None:
        return

    settings = load_settings()
    payload = {
        "event": "origami_api_operation",
        "action": action,
        "environment": settings.environment,
        "request_id": getattr(request.state, "request_id", _request_id(request)),
        "actor": getattr(request.state, "actor", _request_actor(request, settings)),
        "source_ip": getattr(request.state, "source_ip", _source_ip(request)),
        "method": request.method,
        "path": request.url.path,
        "status_code": status_code,
        "target": target,
        "run_id": run_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "metadata": metadata or {},
    }
    LOGGER.info(json.dumps(payload, sort_keys=True, default=str))


def _auth_error_response(request: Request) -> JSONResponse | None:
    settings = load_settings()
    if not _path_requires_auth(request.url.path, settings):
        return None

    if not settings.api_token:
        return JSONResponse(
            status_code=503,
            content={"detail": "API authentication is required but ORIGAMI_API_TOKEN is not set"},
        )

    supplied_token = _request_token(request)
    if supplied_token and secrets.compare_digest(supplied_token, settings.api_token):
        return None

    return JSONResponse(
        status_code=401,
        content={"detail": "Authentication required"},
        headers={"WWW-Authenticate": "Bearer"},
    )


def _path_requires_auth(path: str, settings: OrigamiSettings) -> bool:
    if path == "/metrics":
        return settings.metrics_auth_required
    if path in {"/health", "/api/health", "/api/runtime-config", "/dashboard"}:
        return False
    if path.startswith("/dashboard/static/"):
        return False

    protected_prefixes = (
        "/runs",
        "/benchmarks",
        "/api/reports",
        "/api/events",
        "/api/audit",
        "/api/history",
        "/api/scenarios",
        "/api/multistep-scenarios",
    )
    return settings.auth_required and any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in protected_prefixes
    )


def _request_token(request: Request) -> str:
    header_token = request.headers.get("x-origami-token", "").strip()
    if header_token:
        return header_token

    authorization = request.headers.get("authorization", "").strip()
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() == "bearer":
        return token.strip()
    return ""


def _artifact_path(default_path: Path) -> Path:
    if default_path.is_absolute():
        return default_path
    if default_path.parts and default_path.parts[0] == "artifacts":
        return ARTIFACT_ROOT.joinpath(*default_path.parts[1:])
    return ARTIFACT_ROOT / default_path


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


def _scenario_http_error(exc: ValueError) -> HTTPException:
    status_code = 404 if "not found" in str(exc).lower() else 400
    return HTTPException(status_code=status_code, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
