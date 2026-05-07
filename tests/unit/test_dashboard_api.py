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
    run_history_detail,
    scenario_create,
    scenario_delete,
    scenario_detail,
    scenario_configs,
    scenario_audit,
    scenario_events,
    scenario_run,
    scenario_run_one,
    scenario_update,
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
    assert "/api/history/runs/{record_id}" in route_paths
    assert "/api/scenarios" in route_paths
    assert "/api/scenarios/{scenario_id}" in route_paths
    assert "/runs/scenario" in route_paths
    assert "/runs/scenario/{scenario_id}" in route_paths
    assert "/runs/benchmark" in route_paths


def test_dashboard_page_file_is_served() -> None:
    response = dashboard()
    dashboard_path = Path(response.path)

    assert dashboard_path.name == "dashboard.html"
    assert "Origami Artifact Dashboard" in dashboard_path.read_text()
    assert 'data-tab-target="dashboard"' in dashboard_path.read_text()
    assert 'data-tab-target="scenario-builder"' in dashboard_path.read_text()
    assert 'data-tab-target="test-lab"' in dashboard_path.read_text()
    assert 'data-tab-target="run-history"' in dashboard_path.read_text()
    assert "Scenario Manager" in dashboard_path.read_text()
    assert "Test Lab" in dashboard_path.read_text()
    assert "Run Scenarios and Benchmarks" in dashboard_path.read_text()
    assert "Duplicate" in dashboard_path.read_text()
    assert "Search Scenarios" in dashboard_path.read_text()
    assert "Tag Filter" in dashboard_path.read_text()
    assert "Select Visible" in dashboard_path.read_text()
    assert "Clear" in dashboard_path.read_text()
    assert "Observation" in dashboard_path.read_text()
    assert "Expected" in dashboard_path.read_text()
    assert "Fleet" in dashboard_path.read_text()
    assert "Run Queue" in dashboard_path.read_text()
    assert "Search Runs" in dashboard_path.read_text()
    assert "Compare Runs" in dashboard_path.read_text()
    assert "Clear Filters" in dashboard_path.read_text()
    assert "Validation Preview" in dashboard_path.read_text()
    assert "Diff Preview" in dashboard_path.read_text()
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
    single_payload = scenario_run_one("normal_delivery")
    benchmark_payload = benchmark_run()
    expected_scenario_count = len(list(Path("configs/scenarios").glob("*.yaml")))

    assert scenario_payload["quality_gate_passed"] is True
    assert scenario_payload["total"] == expected_scenario_count
    assert single_payload["quality_gate_passed"] is True
    assert single_payload["total"] == 1
    assert single_payload["scenario"]["id"] == "normal_delivery"
    assert benchmark_payload["quality_gate_passed"] is True
    assert benchmark_payload["audit_valid"] is True
    assert "history_record" in scenario_payload
    assert "history_record" in single_payload
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

    detail_payload = run_history_detail(history_payload["records"][0]["id"])

    assert {"available", "path", "record", "data"} <= set(detail_payload)
    assert detail_payload["available"] is True
    assert detail_payload["record"]["id"] == history_payload["records"][0]["id"]
    assert detail_payload["data"]["quality_gate_passed"] is True


def test_dashboard_scenario_config_endpoint_lists_yaml() -> None:
    payload = scenario_configs()
    expected_scenario_count = len(list(Path("configs/scenarios").glob("*.yaml")))

    assert {"available", "path", "count", "scenarios"} <= set(payload)
    assert payload["available"] is True
    assert payload["count"] == expected_scenario_count
    assert "normal_delivery" in {scenario["id"] for scenario in payload["scenarios"]}


def test_dashboard_scenario_manager_endpoints_update_and_delete() -> None:
    scenario_path = Path("configs/scenarios/dashboard_manager_tmp.yaml")
    scenario_path.unlink(missing_ok=True)

    created = scenario_create(
        {
            "id": "dashboard_manager_tmp",
            "name": "Dashboard Manager Tmp",
            "tags": ["custom", "dashboard"],
            "observation": {"position": [0, 0], "target": [1, 1]},
            "expected": {"final_move": "east"},
        }
    )

    detail = scenario_detail(created["scenario"]["id"])
    updated = scenario_update(
        created["scenario"]["id"],
        {
            "id": "dashboard_manager_tmp",
            "name": "Dashboard Manager Edited",
            "tags": ["custom", "edited"],
            "observation": {"position": [0, 0], "target": [2, 2]},
            "expected": {"final_move": "hold", "seom_passed": False},
        },
    )
    deleted = scenario_delete(created["scenario"]["id"])

    assert detail["scenario"]["id"] == "dashboard_manager_tmp"
    assert updated["updated"] is True
    assert updated["scenario"]["name"] == "Dashboard Manager Edited"
    assert deleted["deleted"] is True
