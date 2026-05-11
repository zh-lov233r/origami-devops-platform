"""
中文：运行时设置加载工具，从环境变量读取内部部署所需的服务边界配置。
English: Runtime settings loader for service-boundary configuration used by internal deployments.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class OrigamiSettings:
    """Runtime settings sourced from environment variables."""

    environment: str
    artifact_root: Path
    grafana_url: str
    log_level: str
    allowed_origins: tuple[str, ...]
    trusted_hosts: tuple[str, ...]
    actor_header: str
    api_token: str
    auth_required: bool
    metrics_auth_required: bool


def load_settings(environ: Mapping[str, str] | None = None) -> OrigamiSettings:
    """Load Origami runtime settings from environment variables.

    `ORIGAMI_AUTH_REQUIRED` defaults to enabled when `ORIGAMI_API_TOKEN` is set, which keeps
    local development friction low while making token-backed internal deployments opt in with
    one secret.
    """
    env = os.environ if environ is None else environ
    api_token = env.get("ORIGAMI_API_TOKEN", "").strip()

    return OrigamiSettings(
        environment=env.get("ORIGAMI_ENV", "local").strip() or "local",
        artifact_root=Path(env.get("ORIGAMI_ARTIFACT_ROOT", "artifacts")),
        grafana_url=(
            env.get("ORIGAMI_GRAFANA_URL", "http://127.0.0.1:3000/d/origami-overview?orgId=1")
            .strip()
            or "http://127.0.0.1:3000/d/origami-overview?orgId=1"
        ),
        log_level=env.get("ORIGAMI_LOG_LEVEL", "INFO").strip().upper() or "INFO",
        allowed_origins=_csv_env(env.get("ORIGAMI_ALLOWED_ORIGINS", "")),
        trusted_hosts=_csv_env(env.get("ORIGAMI_TRUSTED_HOSTS", "")),
        actor_header=env.get("ORIGAMI_ACTOR_HEADER", "X-Origami-Actor").strip()
        or "X-Origami-Actor",
        api_token=api_token,
        auth_required=_bool_env(
            env.get("ORIGAMI_AUTH_REQUIRED"),
            default=bool(api_token),
        ),
        metrics_auth_required=_bool_env(
            env.get("ORIGAMI_METRICS_AUTH_REQUIRED"),
            default=False,
        ),
    )


def _bool_env(value: str | None, default: bool) -> bool:
    if value is None:
        return default

    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    return default


def _csv_env(value: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in value.split(",") if item.strip())
