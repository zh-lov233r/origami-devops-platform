"""
中文：Scenario Manager 工具，负责列出、读取、保存、更新和删除 Carry & Go 场景。
English: Scenario Manager utilities for listing, reading, saving, updating, and deleting Carry & Go scenarios.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml


DEFAULT_SCENARIO_DIR = Path("configs/scenarios")
_SCENARIO_ID_PATTERN = re.compile(r"[^a-z0-9_-]+")


def list_scenarios(scenario_dir: Path | str = DEFAULT_SCENARIO_DIR) -> dict[str, Any]:
    """List scenario YAML files with compact metadata for the dashboard."""
    root = Path(scenario_dir)
    if not root.exists():
        return {"available": False, "path": str(root), "count": 0, "scenarios": []}

    scenarios: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.yaml")):
        try:
            loaded = yaml.safe_load(path.read_text())
        except yaml.YAMLError as exc:
            parse_errors.append({"path": str(path), "error": str(exc)})
            continue
        if not isinstance(loaded, dict):
            parse_errors.append({"path": str(path), "error": "Scenario YAML is not a mapping"})
            continue
        scenarios.append(
            {
                "id": loaded.get("id", path.stem),
                "name": loaded.get("name", path.stem),
                "description": loaded.get("description", ""),
                "tags": loaded.get("tags", []),
                "path": str(path),
            }
        )

    payload: dict[str, Any] = {
        "available": not parse_errors,
        "path": str(root),
        "count": len(scenarios),
        "scenarios": scenarios,
    }
    if parse_errors:
        payload["parse_errors"] = parse_errors
    return payload


def save_scenario(
    payload: dict[str, Any],
    scenario_dir: Path | str = DEFAULT_SCENARIO_DIR,
) -> dict[str, Any]:
    """Validate and write one Scenario Manager payload as a YAML scenario file."""
    scenario = _normalize_scenario_payload(payload)
    root = Path(scenario_dir)
    root.mkdir(parents=True, exist_ok=True)
    output_path = root / f"{scenario['id']}.yaml"

    overwrite = bool(payload.get("overwrite", False))
    if output_path.exists() and not overwrite:
        raise ValueError(f"Scenario already exists: {output_path}")

    _write_scenario(output_path, scenario)

    return {
        "saved": True,
        "path": str(output_path),
        "scenario": {
            "id": scenario["id"],
            "name": scenario["name"],
            "tags": scenario["tags"],
            "description": scenario["description"],
        },
    }


def get_scenario(
    scenario_id: str,
    scenario_dir: Path | str = DEFAULT_SCENARIO_DIR,
) -> dict[str, Any]:
    """Load one scenario YAML file for dashboard editing."""
    path = _scenario_path(scenario_id, scenario_dir)
    if not path.exists():
        raise ValueError(f"Scenario not found: {path}")

    try:
        loaded = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid scenario YAML: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"Scenario YAML is not a mapping: {path}")

    return {
        "available": True,
        "path": str(path),
        "scenario": loaded,
    }


def update_scenario(
    scenario_id: str,
    payload: dict[str, Any],
    scenario_dir: Path | str = DEFAULT_SCENARIO_DIR,
) -> dict[str, Any]:
    """Update an existing scenario, allowing safe id renames."""
    current_path = _scenario_path(scenario_id, scenario_dir)
    if not current_path.exists():
        raise ValueError(f"Scenario not found: {current_path}")

    scenario = _normalize_scenario_payload({**payload, "overwrite": True})
    output_path = Path(scenario_dir) / f"{scenario['id']}.yaml"
    if output_path != current_path and output_path.exists():
        raise ValueError(f"Scenario already exists: {output_path}")

    _write_scenario(output_path, scenario)
    if output_path != current_path:
        current_path.unlink()

    return {
        "saved": True,
        "updated": True,
        "path": str(output_path),
        "previous_id": _safe_scenario_id(scenario_id),
        "scenario": {
            "id": scenario["id"],
            "name": scenario["name"],
            "tags": scenario["tags"],
            "description": scenario["description"],
        },
    }


def delete_scenario(
    scenario_id: str,
    scenario_dir: Path | str = DEFAULT_SCENARIO_DIR,
) -> dict[str, Any]:
    """Delete one scenario YAML file."""
    path = _scenario_path(scenario_id, scenario_dir)
    if not path.exists():
        raise ValueError(f"Scenario not found: {path}")

    path.unlink()
    return {
        "deleted": True,
        "id": _safe_scenario_id(scenario_id),
        "path": str(path),
    }


def _scenario_path(scenario_id: str, scenario_dir: Path | str) -> Path:
    safe_id = _safe_scenario_id(str(scenario_id))
    if not safe_id:
        raise ValueError("Scenario id is required")
    return Path(scenario_dir) / f"{safe_id}.yaml"


def _write_scenario(path: Path, scenario: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(
        [
            "# 中文：Scenario Manager 管理的 Carry & Go 场景。",
            "# English: Carry & Go scenario managed by Scenario Manager.",
            "",
            yaml.safe_dump(scenario, sort_keys=False, allow_unicode=True).strip(),
            "",
        ]
    )
    path.write_text(content)


def _normalize_scenario_payload(payload: dict[str, Any]) -> dict[str, Any]:
    raw_id = str(payload.get("id") or payload.get("name") or "").strip()
    scenario_id = _safe_scenario_id(raw_id)
    if not scenario_id:
        raise ValueError("Scenario id is required")

    observation = payload.get("observation", {})
    expected = payload.get("expected", {})
    if not isinstance(observation, dict) or not observation:
        raise ValueError("Scenario observation must be a non-empty object")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("Scenario expected must be a non-empty object")

    normalized_observation = {"mission_type": "carry_go_delivery", **observation}
    normalized_expected = {"audit_valid": True, **expected}
    if "final_move" not in normalized_expected:
        raise ValueError("Scenario expected.final_move is required")

    return {
        "version": int(payload.get("version", 1)),
        "id": scenario_id,
        "name": str(payload.get("name") or scenario_id.replace("_", " ").title()),
        "description": str(payload.get("description") or "Custom Carry & Go scenario."),
        "tags": _normalize_tags(payload.get("tags", [])),
        "observation": normalized_observation,
        "expected": normalized_expected,
    }


def _safe_scenario_id(raw_id: str) -> str:
    lowered = raw_id.lower().strip().replace(" ", "_")
    cleaned = _SCENARIO_ID_PATTERN.sub("_", lowered)
    cleaned = re.sub(r"_+", "_", cleaned).strip("_-")
    return cleaned


def _normalize_tags(raw_tags: Any) -> list[str]:
    if isinstance(raw_tags, str):
        candidates = raw_tags.split(",")
    elif isinstance(raw_tags, list):
        candidates = raw_tags
    else:
        candidates = []

    tags = [str(tag).strip() for tag in candidates if str(tag).strip()]
    if "custom" not in tags:
        tags.insert(0, "custom")
    return tags
