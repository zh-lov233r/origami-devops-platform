"""
中文：生产部署配置单元测试，防止镜像、compose 和 secret 处理回退到开发模式。
English: Unit tests for production deployment config to prevent regressions to dev-mode images, compose, and secrets.
"""

from pathlib import Path

import yaml


def _prod_compose() -> dict:
    return yaml.safe_load(Path("docker-compose.prod.yml").read_text())


def test_production_dockerfile_uses_locked_non_root_runtime() -> None:
    dockerfile = Path("Dockerfile").read_text()

    assert "ARG PYTHON_IMAGE=python:3.11.13-slim-bookworm" in dockerfile
    assert "ARG UV_VERSION=0.11.8" in dockerfile
    assert "uv export --locked --no-dev --format requirements-txt" in dockerfile
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
