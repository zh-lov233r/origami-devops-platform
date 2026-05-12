"""
中文：API 鉴权测试，验证内部部署 token 策略不会影响健康检查和 Prometheus 抓取。
English: API authentication tests verifying internal token policy without breaking health or Prometheus.
"""

import json
import logging

from starlette.requests import Request

from origami.api.app import (
    _auth_error_response,
    _log_operation,
    _path_requires_proxy_identity,
    _request_actor,
    _request_id,
    _source_ip,
    runtime_config,
)
from origami.core.settings import load_settings


def test_settings_enable_auth_when_api_token_is_set() -> None:
    settings = load_settings({"ORIGAMI_API_TOKEN": "dev-token"})

    assert settings.auth_required is True
    assert settings.api_token == "dev-token"
    assert settings.environment == "local"


def test_settings_allow_explicit_local_auth_disable() -> None:
    settings = load_settings(
        {
            "ORIGAMI_API_TOKEN": "dev-token",
            "ORIGAMI_AUTH_REQUIRED": "false",
        }
    )

    assert settings.auth_required is False


def test_settings_parse_internal_access_boundary_env() -> None:
    settings = load_settings(
        {
            "ORIGAMI_ALLOWED_ORIGINS": "https://origami.internal, http://localhost:8000",
            "ORIGAMI_TRUSTED_HOSTS": "origami.internal,localhost",
            "ORIGAMI_ACTOR_HEADER": "X-Internal-User",
            "ORIGAMI_RUN_RETENTION_LIMIT": "250",
            "ORIGAMI_SCENARIO_CONFIG_DIR": "/var/lib/origami/custom-scenarios",
            "ORIGAMI_TRUSTED_PROXY_AUTH_REQUIRED": "true",
        }
    )

    assert settings.allowed_origins == ("https://origami.internal", "http://localhost:8000")
    assert settings.trusted_hosts == ("origami.internal", "localhost")
    assert settings.actor_header == "X-Internal-User"
    assert settings.run_retention_limit == 250
    assert str(settings.scenario_config_dir) == "/var/lib/origami/custom-scenarios"
    assert settings.trusted_proxy_auth_required is True


def test_protected_routes_require_token_when_auth_enabled(monkeypatch) -> None:
    monkeypatch.setenv("ORIGAMI_AUTH_REQUIRED", "true")
    monkeypatch.setenv("ORIGAMI_API_TOKEN", "dev-token")

    missing = _auth_error_response(_request("/api/reports/scenario"))
    wrong = _auth_error_response(_request("/api/reports/scenario", {"X-Origami-Token": "wrong"}))
    allowed = _auth_error_response(
        _request("/api/reports/scenario", {"X-Origami-Token": "dev-token"})
    )
    bearer_allowed = _auth_error_response(
        _request("/runs/smoke", {"Authorization": "Bearer dev-token"})
    )

    assert missing is not None
    assert missing.status_code == 401
    assert json.loads(missing.body)["detail"] == "Authentication required"
    assert wrong is not None
    assert wrong.status_code == 401
    assert allowed is None
    assert bearer_allowed is None


def test_auth_required_without_token_fails_closed(monkeypatch) -> None:
    monkeypatch.setenv("ORIGAMI_AUTH_REQUIRED", "true")
    monkeypatch.delenv("ORIGAMI_API_TOKEN", raising=False)

    response = _auth_error_response(_request("/api/reports/scenario"))

    assert response is not None
    assert response.status_code == 503
    assert "ORIGAMI_API_TOKEN" in json.loads(response.body)["detail"]


def test_health_runtime_config_and_metrics_stay_public_by_default(monkeypatch) -> None:
    monkeypatch.setenv("ORIGAMI_AUTH_REQUIRED", "true")
    monkeypatch.setenv("ORIGAMI_API_TOKEN", "dev-token")
    monkeypatch.delenv("ORIGAMI_METRICS_AUTH_REQUIRED", raising=False)

    health = _auth_error_response(_request("/api/health"))
    runtime_auth = _auth_error_response(_request("/api/runtime-config"))
    metrics = _auth_error_response(_request("/metrics"))
    config = runtime_config()

    assert health is None
    assert runtime_auth is None
    assert metrics is None
    assert config["auth_required"] is True
    assert config["trusted_proxy_auth_required"] is False
    assert config["artifact_root"] == "artifacts"
    assert config["scenario_config_dir"] == "artifacts/configs/scenarios"
    assert config["grafana_url"].endswith("/d/origami-overview?orgId=1")
    assert config["run_retention_limit"] == 500


def test_metrics_can_require_token(monkeypatch) -> None:
    monkeypatch.setenv("ORIGAMI_API_TOKEN", "dev-token")
    monkeypatch.setenv("ORIGAMI_METRICS_AUTH_REQUIRED", "true")

    missing = _auth_error_response(_request("/metrics"))
    allowed = _auth_error_response(_request("/metrics", {"X-Origami-Token": "dev-token"}))

    assert missing is not None
    assert missing.status_code == 401
    assert allowed is None


def test_trusted_proxy_auth_requires_actor_header_for_protected_routes(monkeypatch) -> None:
    monkeypatch.setenv("ORIGAMI_AUTH_REQUIRED", "true")
    monkeypatch.setenv("ORIGAMI_API_TOKEN", "internal-token")
    monkeypatch.setenv("ORIGAMI_TRUSTED_PROXY_AUTH_REQUIRED", "true")

    missing_actor = _auth_error_response(
        _request("/runs/scenario", {"X-Origami-Token": "internal-token"}, method="POST")
    )
    anonymous_actor = _auth_error_response(
        _request(
            "/api/scenarios",
            {
                "X-Origami-Token": "internal-token",
                "X-Origami-Actor": "anonymous",
            },
            method="POST",
        )
    )
    allowed = _auth_error_response(
        _request(
            "/runs/scenario",
            {
                "X-Origami-Token": "internal-token",
                "X-Origami-Actor": "alice@company.com",
            },
            method="POST",
        )
    )

    assert missing_actor is not None
    assert missing_actor.status_code == 401
    assert json.loads(missing_actor.body)["detail"] == "Trusted proxy identity required"
    assert anonymous_actor is not None
    assert anonymous_actor.status_code == 401
    assert allowed is None


def test_trusted_proxy_auth_does_not_require_actor_for_metrics(monkeypatch) -> None:
    monkeypatch.setenv("ORIGAMI_AUTH_REQUIRED", "true")
    monkeypatch.setenv("ORIGAMI_API_TOKEN", "internal-token")
    monkeypatch.setenv("ORIGAMI_METRICS_AUTH_REQUIRED", "true")
    monkeypatch.setenv("ORIGAMI_TRUSTED_PROXY_AUTH_REQUIRED", "true")
    settings = load_settings()

    response = _auth_error_response(_request("/metrics", {"X-Origami-Token": "internal-token"}))

    assert _path_requires_proxy_identity("/metrics", settings) is False
    assert response is None


def test_request_context_helpers_capture_actor_request_id_and_source_ip() -> None:
    request = _request(
        "/runs/scenario",
        {
            "X-Request-ID": "req-123",
            "X-Origami-Actor": "carry-go-dev",
            "X-Forwarded-For": "10.0.0.7, 10.0.0.1",
        },
    )
    settings = load_settings({})

    assert _request_id(request) == "req-123"
    assert _request_actor(request, settings) == "carry-go-dev"
    assert _source_ip(request) == "10.0.0.7"


def test_log_operation_emits_structured_event(caplog) -> None:
    request = _request(
        "/runs/scenario/normal_delivery",
        {
            "X-Request-ID": "req-456",
            "X-Origami-Actor": "carry-go-dev",
            "X-Forwarded-For": "10.0.0.8",
        },
        method="POST",
    )

    with caplog.at_level(logging.INFO, logger="origami.api"):
        _log_operation(
            request,
            "run_scenario",
            status_code=200,
            target="normal_delivery",
            run_id="scenario-123",
            metadata={"quality_gate_passed": True},
        )

    event = json.loads(caplog.records[-1].message)
    assert event["event"] == "origami_api_operation"
    assert event["action"] == "run_scenario"
    assert event["actor"] == "carry-go-dev"
    assert event["request_id"] == "req-456"
    assert event["source_ip"] == "10.0.0.8"
    assert event["run_id"] == "scenario-123"
    assert event["metadata"]["quality_gate_passed"] is True


def _request(
    path: str,
    headers: dict[str, str] | None = None,
    method: str = "GET",
) -> Request:
    header_items = [
        (name.lower().encode("latin-1"), value.encode("latin-1"))
        for name, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "headers": header_items,
            "query_string": b"",
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 50000),
        }
    )
