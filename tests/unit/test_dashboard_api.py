"""
中文：Dashboard API 单元测试，验证 artifact dashboard 页面和报告读取接口可用。
English: Unit tests for the dashboard API ensuring the artifact dashboard page and report endpoints are available.
"""

from pathlib import Path

from origami.api.app import (
    _artifact_path,
    app,
    benchmark_run,
    benchmark_report,
    dashboard,
    multistep_scenario_configs,
    multistep_scenario_audit,
    multistep_scenario_events,
    multistep_scenario_report,
    multistep_scenario_run,
    multistep_scenario_run_one,
    run_history,
    run_history_detail,
    scenario_create,
    scenario_delete,
    scenario_detail,
    scenario_configs,
    scenario_audit,
    scenario_events,
    metrics,
    scenario_run,
    scenario_run_one,
    scenario_update,
    scenario_report,
)


def test_dashboard_routes_are_registered() -> None:
    route_paths = {route.path for route in app.routes}

    assert "/dashboard" in route_paths
    assert "/api/reports/scenario" in route_paths
    assert "/api/reports/multistep-scenario" in route_paths
    assert "/api/reports/benchmark" in route_paths
    assert "/api/events/scenario" in route_paths
    assert "/api/events/multistep-scenario" in route_paths
    assert "/api/audit/scenario" in route_paths
    assert "/api/audit/multistep-scenario" in route_paths
    assert "/api/history/runs" in route_paths
    assert "/api/history/runs/{record_id}" in route_paths
    assert "/api/scenarios" in route_paths
    assert "/api/multistep-scenarios" in route_paths
    assert "/api/scenarios/{scenario_id}" in route_paths
    assert "/runs/scenario" in route_paths
    assert "/runs/scenario/{scenario_id}" in route_paths
    assert "/runs/multistep-scenario" in route_paths
    assert "/runs/multistep-scenario/{scenario_id}" in route_paths
    assert "/runs/benchmark" in route_paths
    assert "/metrics" in route_paths
    assert "/api/runtime-config" in route_paths


def test_dashboard_page_file_is_served() -> None:
    response = dashboard()
    dashboard_path = Path(response.path)

    assert dashboard_path.name == "dashboard.html"
    assert "Origami Artifact Dashboard" in dashboard_path.read_text()
    assert 'data-tab-target="dashboard"' in dashboard_path.read_text()
    assert 'data-tab-target="scenario-builder"' in dashboard_path.read_text()
    assert 'data-tab-target="test-lab"' in dashboard_path.read_text()
    assert 'data-tab-target="run-history"' in dashboard_path.read_text()
    assert 'id="observability-button"' in dashboard_path.read_text()
    assert 'id="api-token-input"' in dashboard_path.read_text()
    assert 'id="auth-status"' in dashboard_path.read_text()
    assert "http://127.0.0.1:3000/d/origami-overview?orgId=1" in dashboard_path.read_text()
    assert "Scenario Manager" in dashboard_path.read_text()
    assert "Test Lab" in dashboard_path.read_text()
    assert "Run Scenarios and Benchmarks" in dashboard_path.read_text()
    assert "Multi-Step Timeline" in dashboard_path.read_text()
    assert 'id="run-multistep-scenario-button"' in dashboard_path.read_text()
    assert 'id="test-multistep-scenario-select"' in dashboard_path.read_text()
    assert "Duplicate" in dashboard_path.read_text()
    assert "Search Scenarios" in dashboard_path.read_text()
    assert "Tag Filter" in dashboard_path.read_text()
    assert "Select Visible" in dashboard_path.read_text()
    assert "Clear" in dashboard_path.read_text()
    assert "Observation" in dashboard_path.read_text()
    assert "Expected" in dashboard_path.read_text()
    assert "Fleet" in dashboard_path.read_text()
    assert "Run Queue" in dashboard_path.read_text()
    assert "Safety Signals" in dashboard_path.read_text()
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
    multistep_payload = multistep_scenario_report()
    benchmark_payload = benchmark_report()

    assert {"available", "path", "data"} <= set(scenario_payload)
    assert {"available", "path", "data"} <= set(multistep_payload)
    assert {"available", "path", "data"} <= set(benchmark_payload)


def test_artifact_paths_follow_configured_root(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("origami.api.app.ARTIFACT_ROOT", tmp_path)

    assert _artifact_path(Path("artifacts/reports/scenario_report.json")) == (
        tmp_path / "reports/scenario_report.json"
    )
    assert _artifact_path(Path("reports/custom.json")) == tmp_path / "reports/custom.json"


def test_dashboard_multistep_config_endpoint_lists_yaml() -> None:
    payload = multistep_scenario_configs()
    expected_count = len(list(Path("configs/multistep_scenarios").glob("*.yaml")))

    assert {"available", "path", "count", "scenarios"} <= set(payload)
    assert payload["available"] is True
    assert payload["count"] == expected_count
    assert "delivery_long_return_interruption" in {
        scenario["id"] for scenario in payload["scenarios"]
    }


def test_dashboard_jsonl_endpoints_return_record_payloads() -> None:
    events_payload = scenario_events(limit=5)
    multistep_events_payload = multistep_scenario_events(limit=5)
    audit_payload = scenario_audit(limit=5)
    multistep_audit_payload = multistep_scenario_audit(limit=5)

    assert {"available", "path", "count", "records"} <= set(events_payload)
    assert {"available", "path", "count", "records"} <= set(multistep_events_payload)
    assert {"available", "path", "count", "records"} <= set(audit_payload)
    assert {"available", "path", "count", "records"} <= set(multistep_audit_payload)
    assert len(events_payload["records"]) <= 5
    assert len(multistep_events_payload["records"]) <= 5
    assert len(audit_payload["records"]) <= 5
    assert len(multistep_audit_payload["records"]) <= 5


def test_metrics_endpoint_exposes_prometheus_payload() -> None:
    scenario_run_one("normal_delivery")
    benchmark_run()

    response = metrics()
    body = response.body.decode()

    assert response.media_type.startswith("text/plain")
    assert "origami_app_info" in body
    assert "origami_http_requests_total" in body
    assert "origami_http_request_duration_seconds" in body
    assert 'origami_run_quality_gate{run_type="scenario",scope="normal_delivery"} 1.0' in body
    assert 'origami_scenario_pass_rate{scope="normal_delivery",suite="carry_go"} 1.0' in body
    assert (
        'origami_scenario_safety_signal_cases{'
        'scope="normal_delivery",status="none",suite="carry_go"} 1.0'
    ) in body
    assert (
        'origami_scenario_safety_signal_cases{'
        'scope="normal_delivery",status="unexpected",suite="carry_go"} 0.0'
    ) in body
    assert 'origami_run_quality_gate{run_type="benchmark",scope="default"} 1.0' in body
    assert 'origami_benchmark_steps{scope="default"} 20.0' in body


def test_dashboard_run_actions_write_reports(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("origami.api.app.CUSTOM_SCENARIO_DIR", tmp_path / "custom-scenarios")

    scenario_payload = scenario_run()
    single_payload = scenario_run_one("normal_delivery")
    multistep_payload = multistep_scenario_run()
    single_multistep_payload = multistep_scenario_run_one("delivery_low_battery_return")
    benchmark_payload = benchmark_run()
    expected_scenario_count = len(list(Path("configs/scenarios").glob("*.yaml")))
    expected_multistep_count = len(list(Path("configs/multistep_scenarios").glob("*.yaml")))

    assert scenario_payload["quality_gate_passed"] is True
    assert scenario_payload["total"] == expected_scenario_count
    assert single_payload["quality_gate_passed"] is True
    assert single_payload["total"] == 1
    assert single_payload["scenario"]["id"] == "normal_delivery"
    assert multistep_payload["quality_gate_passed"] is True
    assert multistep_payload["total"] == expected_multistep_count
    assert single_multistep_payload["quality_gate_passed"] is True
    assert single_multistep_payload["scenario"]["id"] == "delivery_low_battery_return"
    assert benchmark_payload["quality_gate_passed"] is True
    assert benchmark_payload["audit_valid"] is True
    assert "history_record" in scenario_payload
    assert "history_record" in single_payload
    assert "history_record" in multistep_payload
    assert "history_record" in single_multistep_payload
    assert "history_record" in benchmark_payload
    assert scenario_payload["history_record"]["id"] == scenario_payload["run_id"]
    assert single_payload["history_record"]["id"] == single_payload["run_id"]
    assert multistep_payload["history_record"]["id"] == multistep_payload["run_id"]
    assert single_multistep_payload["history_record"]["id"] == single_multistep_payload["run_id"]
    assert benchmark_payload["history_record"]["id"] == benchmark_payload["run_id"]
    for payload in (
        scenario_payload,
        single_payload,
        multistep_payload,
        single_multistep_payload,
        benchmark_payload,
    ):
        assert Path(payload["history_record"]["artifact_dir"]).exists()
        assert Path(payload["history_record"]["artifact_path"]).exists()


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
    assert detail_payload["data"]["run_id"] == history_payload["records"][0]["id"]
    assert {"json_report", "event_log", "audit_log"} <= set(
        detail_payload["record"].get("artifacts", {})
    )


def test_dashboard_scenario_config_endpoint_lists_yaml(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("origami.api.app.CUSTOM_SCENARIO_DIR", tmp_path / "custom-scenarios")

    payload = scenario_configs()
    expected_scenario_count = len(list(Path("configs/scenarios").glob("*.yaml")))

    assert {"available", "path", "overlay_path", "count", "scenarios"} <= set(payload)
    assert payload["available"] is True
    assert payload["count"] == expected_scenario_count
    assert "normal_delivery" in {scenario["id"] for scenario in payload["scenarios"]}
    assert all(scenario["source"] == "built_in" for scenario in payload["scenarios"])


def test_dashboard_scenario_manager_endpoints_update_and_delete(monkeypatch, tmp_path: Path) -> None:
    custom_dir = tmp_path / "custom-scenarios"
    monkeypatch.setattr("origami.api.app.CUSTOM_SCENARIO_DIR", custom_dir)

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

    assert Path(created["path"]).parent == custom_dir
    assert detail["scenario"]["id"] == "dashboard_manager_tmp"
    assert detail["source"] == "custom"
    assert detail["delete_allowed"] is True
    assert updated["updated"] is True
    assert updated["scenario"]["name"] == "Dashboard Manager Edited"
    assert deleted["deleted"] is True
    assert not (custom_dir / "dashboard_manager_tmp.yaml").exists()
