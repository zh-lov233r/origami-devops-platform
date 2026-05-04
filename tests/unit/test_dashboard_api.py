"""
中文：Dashboard API 单元测试，验证 artifact dashboard 页面和报告读取接口可用。
English: Unit tests for the dashboard API ensuring the artifact dashboard page and report endpoints are available.
"""

from pathlib import Path

from origami.api.app import (
    app,
    benchmark_run,
    benchmark_report,
    dashboard,
    run_history,
    scenario_configs,
    scenario_audit,
    scenario_events,
    scenario_run,
    scenario_report,
)


def test_dashboard_routes_are_registered() -> None:
    route_paths = {route.path for route in app.routes}

    assert "/dashboard" in route_paths
    assert "/api/reports/scenario" in route_paths
    assert "/api/reports/benchmark" in route_paths
    assert "/api/events/scenario" in route_paths
    assert "/api/audit/scenario" in route_paths
    assert "/api/history/runs" in route_paths
    assert "/api/scenarios" in route_paths
    assert "/runs/scenario" in route_paths
    assert "/runs/benchmark" in route_paths


def test_dashboard_page_file_is_served() -> None:
    response = dashboard()
    dashboard_path = Path(response.path)

    assert dashboard_path.name == "dashboard.html"
    assert "Origami Artifact Dashboard" in dashboard_path.read_text()
    assert 'data-tab-target="dashboard"' in dashboard_path.read_text()
    assert 'data-tab-target="scenario-builder"' in dashboard_path.read_text()
    assert 'data-tab-target="run-history"' in dashboard_path.read_text()
    assert "Scenario Builder" in dashboard_path.read_text()
    assert "Advanced Options" in dashboard_path.read_text()
    assert "Outcome Split" in dashboard_path.read_text()
    assert "Max P95 Trend" in dashboard_path.read_text()
    assert "Violation Distribution" in dashboard_path.read_text()


def test_dashboard_report_endpoints_return_artifact_payloads() -> None:
    scenario_payload = scenario_report()
    benchmark_payload = benchmark_report()

    assert {"available", "path", "data"} <= set(scenario_payload)
    assert {"available", "path", "data"} <= set(benchmark_payload)


def test_dashboard_jsonl_endpoints_return_record_payloads() -> None:
    events_payload = scenario_events(limit=5)
    audit_payload = scenario_audit(limit=5)

    assert {"available", "path", "count", "records"} <= set(events_payload)
    assert {"available", "path", "count", "records"} <= set(audit_payload)
    assert len(events_payload["records"]) <= 5
    assert len(audit_payload["records"]) <= 5


def test_dashboard_run_actions_write_reports() -> None:
    scenario_payload = scenario_run()
    benchmark_payload = benchmark_run()

    assert scenario_payload["quality_gate_passed"] is True
    assert scenario_payload["total"] == 8
    assert benchmark_payload["quality_gate_passed"] is True
    assert benchmark_payload["audit_valid"] is True
    assert "history_record" in scenario_payload
    assert "history_record" in benchmark_payload


def test_dashboard_history_endpoint_returns_recent_runs() -> None:
    scenario_run()
    benchmark_run()

    history_payload = run_history(limit=5)

    assert {"available", "path", "count", "records"} <= set(history_payload)
    assert history_payload["available"] is True
    assert history_payload["count"] >= 2
    assert len(history_payload["records"]) <= 5
    assert history_payload["records"][0]["type"] in {"scenario", "benchmark"}


def test_dashboard_scenario_config_endpoint_lists_yaml() -> None:
    payload = scenario_configs()

    assert {"available", "path", "count", "scenarios"} <= set(payload)
    assert payload["available"] is True
    assert payload["count"] >= 8
    assert "normal_delivery" in {scenario["id"] for scenario in payload["scenarios"]}
