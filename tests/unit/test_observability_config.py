"""
中文：Observability 配置单元测试，验证 Prometheus scrape 与 alert rule 配置可解析。
English: Unit tests for observability config ensuring Prometheus scrape and alert rules parse.
"""

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
        "OrigamiModuleP95High",
    } <= alert_names
