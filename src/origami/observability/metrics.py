"""
中文：Prometheus 指标辅助模块，暴露 HTTP 与业务运行指标。
English: Prometheus metric helpers exposing HTTP and business run metrics.
"""

from __future__ import annotations

from typing import Any

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)


METRICS_REGISTRY = CollectorRegistry()
PROMETHEUS_CONTENT_TYPE = CONTENT_TYPE_LATEST

HTTP_REQUESTS_TOTAL = Counter(
    "origami_http_requests_total",
    "Total FastAPI HTTP requests.",
    ("method", "path", "status_code"),
    registry=METRICS_REGISTRY,
)
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "origami_http_request_duration_seconds",
    "FastAPI HTTP request duration in seconds.",
    ("method", "path"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0),
    registry=METRICS_REGISTRY,
)
APP_INFO = Gauge(
    "origami_app_info",
    "Origami control-plane application info.",
    ("app",),
    registry=METRICS_REGISTRY,
)
RUN_QUALITY_GATE = Gauge(
    "origami_run_quality_gate",
    "Latest quality-gate status for a run type and scope, 1 for pass and 0 for fail.",
    ("run_type", "scope"),
    registry=METRICS_REGISTRY,
)
RUN_MAX_MODULE_P95_MS = Gauge(
    "origami_run_max_module_p95_ms",
    "Latest maximum module p95 latency in milliseconds for a run type and scope.",
    ("run_type", "scope"),
    registry=METRICS_REGISTRY,
)
RUN_MODULE_LATENCY_MS = Gauge(
    "origami_run_module_latency_ms",
    "Latest module latency summary in milliseconds.",
    ("run_type", "scope", "module", "stat"),
    registry=METRICS_REGISTRY,
)
SCENARIO_PASS_RATE = Gauge(
    "origami_scenario_pass_rate",
    "Latest scenario pass rate for a scenario scope.",
    ("scope", "suite"),
    registry=METRICS_REGISTRY,
)
SCENARIO_CASES = Gauge(
    "origami_scenario_cases",
    "Latest scenario case counts by result.",
    ("scope", "suite", "result"),
    registry=METRICS_REGISTRY,
)
SCENARIO_VIOLATION_COUNT = Gauge(
    "origami_scenario_violation_count",
    "Latest scenario violation count.",
    ("scope", "suite"),
    registry=METRICS_REGISTRY,
)
BENCHMARK_STEPS = Gauge(
    "origami_benchmark_steps",
    "Latest benchmark step count.",
    ("scope",),
    registry=METRICS_REGISTRY,
)
BENCHMARK_AUDIT_VALID = Gauge(
    "origami_benchmark_audit_valid",
    "Latest benchmark audit validity, 1 for valid and 0 for invalid.",
    ("scope",),
    registry=METRICS_REGISTRY,
)

APP_INFO.labels(app="origami-devops-platform").set(1)


def render_metrics() -> bytes:
    """Return the current Prometheus exposition payload."""
    return generate_latest(METRICS_REGISTRY)


def record_http_request(method: str, path: str, status_code: int, elapsed_seconds: float) -> None:
    """Record one HTTP request observation."""
    HTTP_REQUESTS_TOTAL.labels(
        method=method,
        path=path,
        status_code=str(status_code),
    ).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(
        method=method,
        path=path,
    ).observe(elapsed_seconds)


def record_scenario_report(report: dict[str, Any], scope: str = "suite") -> None:
    """Publish gauges for the latest scenario run report."""
    suite = str(report.get("suite") or "unknown")
    RUN_QUALITY_GATE.labels(run_type="scenario", scope=scope).set(
        _bool_value(report.get("quality_gate_passed")),
    )
    SCENARIO_PASS_RATE.labels(scope=scope, suite=suite).set(_float_value(report.get("pass_rate")))
    for result in ("total", "passed", "failed"):
        SCENARIO_CASES.labels(scope=scope, suite=suite, result=result).set(
            _float_value(report.get(result)),
        )
    SCENARIO_VIOLATION_COUNT.labels(scope=scope, suite=suite).set(_violation_count(report))
    _record_module_latency("scenario", scope, report)


def record_benchmark_report(report: dict[str, Any], scope: str = "default") -> None:
    """Publish gauges for the latest benchmark report."""
    RUN_QUALITY_GATE.labels(run_type="benchmark", scope=scope).set(
        _bool_value(report.get("quality_gate_passed")),
    )
    BENCHMARK_STEPS.labels(scope=scope).set(_float_value(report.get("steps")))
    BENCHMARK_AUDIT_VALID.labels(scope=scope).set(_bool_value(report.get("audit_valid")))
    _record_module_latency("benchmark", scope, report)


def _record_module_latency(run_type: str, scope: str, report: dict[str, Any]) -> None:
    metrics = _module_latency(report)
    max_p95_ms = max(
        (_float_value(module_metrics.get("p95")) for module_metrics in metrics.values()),
        default=0.0,
    )
    RUN_MAX_MODULE_P95_MS.labels(run_type=run_type, scope=scope).set(max_p95_ms)

    for module, module_metrics in metrics.items():
        for stat in ("avg", "p50", "p95", "max"):
            if stat in module_metrics:
                RUN_MODULE_LATENCY_MS.labels(
                    run_type=run_type,
                    scope=scope,
                    module=str(module),
                    stat=stat,
                ).set(_float_value(module_metrics.get(stat)))


def _module_latency(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    direct_latency = report.get("module_latency_ms")
    if isinstance(direct_latency, dict):
        return _dict_metrics(direct_latency)

    summary = report.get("summary", {})
    summary_latency = summary.get("module_latency_ms") if isinstance(summary, dict) else None
    if isinstance(summary_latency, dict):
        return _dict_metrics(summary_latency)
    return {}


def _dict_metrics(raw_metrics: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(module): metrics
        for module, metrics in raw_metrics.items()
        if isinstance(metrics, dict)
    }


def _violation_count(report: dict[str, Any]) -> float:
    summary = report.get("summary", {})
    violation_counts = summary.get("violation_counts", {}) if isinstance(summary, dict) else {}
    if not isinstance(violation_counts, dict):
        return 0.0
    return sum(_float_value(count) for count in violation_counts.values())


def _bool_value(value: Any) -> float:
    return 1.0 if value is True else 0.0


def _float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
