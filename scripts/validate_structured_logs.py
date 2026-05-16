#!/usr/bin/env python3
"""
中文：验证 Origami API structured operation log，供 staging smoke 或人工验收使用。
English: Validate Origami API structured operation logs for staging smoke or manual acceptance.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any


REQUIRED_FIELDS = {
    "action",
    "actor",
    "environment",
    "event",
    "metadata",
    "method",
    "path",
    "request_id",
    "run_id",
    "source_ip",
    "status_code",
    "target",
    "timestamp",
}


def main() -> int:
    args = _parse_args()
    lines = _read_lines(args.log_file)
    result = validate_lines(lines, require_run_id=args.require_run_id)
    if result["valid"]:
        print(
            "Structured log validation passed: "
            f"{result['operation_events']} operation events checked."
        )
        return 0

    print("Structured log validation failed:", file=sys.stderr)
    for error in result["errors"]:
        print(f"- {error}", file=sys.stderr)
    return 1


def validate_lines(lines: Iterable[str], require_run_id: bool = False) -> dict[str, Any]:
    errors: list[str] = []
    event_count = 0
    run_id_count = 0

    for line_number, raw_line in enumerate(lines, start=1):
        line = raw_line.strip()
        if not line:
            continue

        payload = _parse_log_payload(line)
        if payload is None or payload.get("event") != "origami_api_operation":
            continue

        event_count += 1
        missing = sorted(field for field in REQUIRED_FIELDS if field not in payload)
        if missing:
            errors.append(f"line {line_number}: missing required fields: {', '.join(missing)}")
            continue

        for field in ("action", "actor", "environment", "method", "path", "request_id", "source_ip"):
            if not str(payload.get(field, "")).strip():
                errors.append(f"line {line_number}: field {field} must be non-empty")

        if not isinstance(payload.get("status_code"), int):
            errors.append(f"line {line_number}: field status_code must be an integer")
        if not isinstance(payload.get("metadata"), dict):
            errors.append(f"line {line_number}: field metadata must be an object")

        run_id = payload.get("run_id")
        if isinstance(run_id, str) and run_id.strip():
            run_id_count += 1

    if event_count == 0:
        errors.append("no origami_api_operation events found")
    if require_run_id and run_id_count == 0:
        errors.append("no origami_api_operation events with run_id found")

    return {
        "valid": not errors,
        "errors": errors,
        "operation_events": event_count,
        "operation_events_with_run_id": run_id_count,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Origami structured operation logs.")
    parser.add_argument(
        "log_file",
        nargs="?",
        help="Log file to validate. Reads stdin when omitted.",
    )
    parser.add_argument(
        "--require-run-id",
        action="store_true",
        help="Require at least one operation event with a non-empty run_id.",
    )
    return parser.parse_args()


def _read_lines(log_file: str | None) -> list[str]:
    if log_file:
        return Path(log_file).read_text().splitlines()
    return sys.stdin.read().splitlines()


def _parse_log_payload(line: str) -> dict[str, Any] | None:
    json_start = line.find("{")
    if json_start < 0:
        return None

    try:
        payload = json.loads(line[json_start:])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


if __name__ == "__main__":
    raise SystemExit(main())
