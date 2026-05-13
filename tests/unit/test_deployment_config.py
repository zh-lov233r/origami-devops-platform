"""
中文：生产部署配置单元测试，防止镜像、compose 和 secret 处理回退到开发模式。
English: Unit tests for production deployment config to prevent regressions to dev-mode images, compose, and secrets.
"""

from pathlib import Path

import yaml


def _prod_compose() -> dict:
    return yaml.safe_load(Path("docker-compose.prod.yml").read_text())


def _sso_compose() -> dict:
    return yaml.safe_load(Path("docker-compose.sso.yml").read_text())


def test_production_dockerfile_uses_locked_non_root_runtime() -> None:
    dockerfile = Path("Dockerfile").read_text()

    assert "ARG PYTHON_IMAGE=python:3.11.13-slim-bookworm" in dockerfile
    assert "ARG UV_VERSION=0.11.8" in dockerfile
    assert "apt-get upgrade -y --no-install-recommends" in dockerfile
    assert "uv export --locked --no-dev --format requirements-txt" in dockerfile
    assert "python -m pip uninstall -y uv setuptools wheel" in dockerfile
    assert "COPY --chown=origami:origami configs ./configs" in dockerfile
    assert "COPY --chown=origami:origami src ./src" in dockerfile
    assert "ENV ORIGAMI_ARTIFACT_ROOT=/var/lib/origami/artifacts" in dockerfile
    assert "USER origami" in dockerfile
    assert "COPY . ." not in dockerfile


def test_production_compose_pins_images_and_uses_persistent_volumes() -> None:
    compose = _prod_compose()
    services = compose["services"]
    image_refs = [service["image"] for service in services.values() if "image" in service]

    assert services["api"]["image"] == "${ORIGAMI_API_IMAGE:-origami-devops-platform-api:0.1.0}"
    assert services["prometheus"]["image"] == "prom/prometheus:v2.55.1"
    assert services["grafana"]["image"] == "grafana/grafana:11.4.0"
    assert all(not image_ref.endswith(":latest") for image_ref in image_refs)

    assert "origami-artifacts:/var/lib/origami/artifacts" in services["api"]["volumes"]
    assert {"origami-artifacts", "prometheus-data", "grafana-data"} <= set(
        compose["volumes"]
    )


def test_production_compose_keeps_dev_mounts_out_and_hardens_services() -> None:
    compose = _prod_compose()
    services = compose["services"]

    for service in services.values():
        assert ".:/workspace" not in service.get("volumes", [])
        assert service["restart"] == "unless-stopped"
        assert "healthcheck" in service
        assert service["cap_drop"] == ["ALL"]
        assert "no-new-privileges:true" in service["security_opt"]
        assert "deploy" in service

    assert services["api"]["read_only"] is True
    assert services["prometheus"]["read_only"] is True
    assert "/tmp" in services["api"]["tmpfs"]
    assert "/tmp" in services["prometheus"]["tmpfs"]
    assert services["api"]["ports"] == ["${ORIGAMI_API_BIND:-127.0.0.1:8000}:8000"]
    assert services["prometheus"]["ports"] == ["${PROMETHEUS_BIND:-127.0.0.1:9090}:9090"]
    assert services["grafana"]["ports"] == ["${GRAFANA_BIND:-127.0.0.1:3000}:3000"]


def test_production_grafana_and_env_example_require_controlled_credentials() -> None:
    compose = _prod_compose()
    grafana_env = compose["services"]["grafana"]["environment"]
    env_example = Path(".env.production.example").read_text()

    assert grafana_env["GF_AUTH_ANONYMOUS_ENABLED"] == "false"
    assert grafana_env["GF_SECURITY_ADMIN_USER"] == "${GRAFANA_ADMIN_USER:?Set GRAFANA_ADMIN_USER}"
    assert grafana_env["GF_SECURITY_ADMIN_PASSWORD"] == (
        "${GRAFANA_ADMIN_PASSWORD:?Set GRAFANA_ADMIN_PASSWORD}"
    )
    assert "ORIGAMI_API_TOKEN=replace-with-internal-token" in env_example
    assert "GRAFANA_ADMIN_PASSWORD=replace-with-strong-password" in env_example
    assert "ORIGAMI_RUN_RETENTION_LIMIT=500" in env_example
    assert "ORIGAMI_SCENARIO_CONFIG_DIR=/var/lib/origami/artifacts/configs/scenarios" in env_example
    assert "ORIGAMI_TRUSTED_PROXY_AUTH_REQUIRED=true" in env_example
    assert compose["services"]["api"]["environment"]["ORIGAMI_RUN_RETENTION_LIMIT"] == (
        "${ORIGAMI_RUN_RETENTION_LIMIT:-500}"
    )
    assert compose["services"]["api"]["environment"]["ORIGAMI_SCENARIO_CONFIG_DIR"] == (
        "${ORIGAMI_SCENARIO_CONFIG_DIR:-/var/lib/origami/artifacts/configs/scenarios}"
    )


def test_sso_compose_adds_google_workspace_auth_proxy() -> None:
    compose = _sso_compose()
    services = compose["services"]
    oauth_env = services["oauth2-proxy"]["environment"]
    api_env = services["api"]["environment"]

    assert services["oauth2-proxy"]["image"] == "quay.io/oauth2-proxy/oauth2-proxy:v7.15.2"
    assert services["sso-proxy"]["image"] == "nginx:1.29.8-alpine"
    assert api_env["ORIGAMI_TRUSTED_PROXY_AUTH_REQUIRED"] == (
        "${ORIGAMI_TRUSTED_PROXY_AUTH_REQUIRED:-true}"
    )
    assert api_env["ORIGAMI_ACTOR_HEADER"] == "X-Origami-Actor"

    assert oauth_env["OAUTH2_PROXY_PROVIDER"] == "google"
    assert oauth_env["OAUTH2_PROXY_EMAIL_DOMAINS"] == (
        "${GOOGLE_WORKSPACE_DOMAIN:?Set GOOGLE_WORKSPACE_DOMAIN}"
    )
    assert oauth_env["OAUTH2_PROXY_SET_XAUTHREQUEST"] == "true"
    assert oauth_env["OAUTH2_PROXY_PASS_USER_HEADERS"] == "true"
    assert oauth_env["OAUTH2_PROXY_UPSTREAMS"] == "static://202"
    assert services["sso-proxy"]["ports"] == ["${ORIGAMI_SSO_BIND:-127.0.0.1:8080}:8080"]
    assert "configs/auth/nginx/origami-sso.conf.template" in services["sso-proxy"]["volumes"][0]
    assert "scripts/render_nginx_sso_config.sh" in services["sso-proxy"]["volumes"][1]
    assert "/etc/nginx/conf.d" in services["sso-proxy"]["tmpfs"]
    assert services["sso-proxy"]["cap_drop"] == ["ALL"]
    assert services["sso-proxy"]["cap_add"] == ["CHOWN", "SETGID", "SETUID"]
    assert services["sso-proxy"]["command"] == [
        "/bin/sh",
        "/usr/local/bin/render_nginx_sso_config.sh",
    ]


def test_nginx_sso_template_injects_only_trusted_identity_headers() -> None:
    template = Path("configs/auth/nginx/origami-sso.conf.template").read_text()

    assert "auth_request /oauth2/auth;" in template
    assert "location = /api/health" in template
    assert "X-Auth-Request-Redirect $scheme://$http_host$request_uri;" in template
    assert "return 302 /oauth2/start?rd=$scheme://$http_host$request_uri;" in template
    assert "auth_request_set $email $upstream_http_x_auth_request_email;" in template
    assert "proxy_set_header X-Origami-Actor $email;" in template
    assert 'proxy_set_header X-Origami-Token "__ORIGAMI_API_TOKEN__";' in template
    assert 'proxy_set_header Authorization "";' in template
    assert 'proxy_set_header X-Auth-Request-Email "";' in template
    assert "proxy_pass http://api:8000;" in template


def test_nginx_sso_render_script_replaces_api_token_placeholder() -> None:
    script = Path("scripts/render_nginx_sso_config.sh").read_text()

    assert "ORIGAMI_API_TOKEN" in script
    assert "__ORIGAMI_API_TOKEN__" in script
    assert "exec nginx -g" in script
