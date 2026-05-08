"""
中文：Observability 配置单元测试，验证 Prometheus scrape 与 alert rule 配置可解析。
English: Unit tests for observability config ensuring Prometheus scrape and alert rules parse.
"""

import json
from pathlib import Path

import yaml


def test_prometheus_config_loads_alert_rules() -> None:
    config = yaml.safe_load(Path("configs/observability/prometheus.yml").read_text())

    assert "/etc/prometheus/rules/*.yml" in config["rule_files"]
    assert config["scrape_configs"][0]["job_name"] == "origami-api"
    assert config["scrape_configs"][0]["static_configs"][0]["targets"] == ["api:8000"]


def test_origami_alert_rules_are_defined() -> None:
    rules = yaml.safe_load(Path("configs/observability/rules/origami-alerts.yml").read_text())
    alert_names = {
        rule["alert"]
        for group in rules["groups"]
        for rule in group["rules"]
    }

    assert {
        "OrigamiApiDown",
        "OrigamiApiHigh5xxRate",
        "OrigamiApiHighP95Latency",
        "OrigamiScenarioGateFailed",
        "OrigamiBenchmarkGateFailed",
        "OrigamiScenarioPassRateLow",
        "OrigamiScenarioSafetySignalMismatch",
        "OrigamiModuleP95High",
    } <= alert_names


def test_grafana_dashboard_tracks_safety_signals() -> None:
    dashboard = json.loads(
        Path("configs/observability/grafana/dashboards/origami-overview.json").read_text()
    )
    target_exprs = {
        target["expr"]
        for panel in dashboard["panels"]
        for target in panel.get("targets", [])
    }
    panel_titles = {panel["title"] for panel in dashboard["panels"]}

    assert "origami_scenario_safety_signal_cases" in target_exprs
    assert "Scenario Safety Signals" in panel_titles
