"""
中文：配置加载工具，负责从 YAML 文件读取可复现实验和运行设置。
English: Configuration loading utilities for reading reproducible experiment and runtime settings from YAML files.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def load_config(path: str | Path) -> dict[str, Any]:
    """Load YAML config when PyYAML is installed."""
    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("Install pyyaml to load YAML configs.") from exc

    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    return data or {}
