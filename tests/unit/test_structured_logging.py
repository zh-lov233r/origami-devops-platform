"""
中文：Structured logging 运维回归测试，验证日志字段契约和 runbook wiring。
English: Structured logging operations regression tests for log field contract and runbook wiring.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.validate_structured_logs import validate_lines


def test_structured_log_validator_accepts_operation_event_with_request_and_run_ids() -> None:
    event = {
        "event": "origami_api_operation",
        "action": "run_scenario",
        "environment": "staging",
        "request_id": "req-123",
        "actor": "dev@example.com",
        "source_ip": "10.0.0.7",
        "method": "POST",
        "path": "/runs/scenario/normal_delivery",
        "status_code": 200,
        "target": "normal_delivery",
        "run_id": "scenario-123",
        "timestamp": "2026-05-16T18:00:00+00:00",
        "metadata": {"quality_gate_passed": True},
    }

    result = validate_lines([f"INFO:origami.api:{json.dumps(event)}"], require_run_id=True)

    assert result == {
        "valid": True,
        "errors": [],
        "operation_events": 1,
        "operation_events_with_run_id": 1,
    }


def test_structured_log_validator_rejects_missing_run_id_when_required() -> None:
    event = {
        "event": "origami_api_operation",
        "action": "scenario_create",
        "environment": "staging",
        "request_id": "req-123",
        "actor": "dev@example.com",
        "source_ip": "10.0.0.7",
        "method": "POST",
        "path": "/api/scenarios",
        "status_code": 200,
        "target": "custom",
        "run_id": None,
        "timestamp": "2026-05-16T18:00:00+00:00",
        "metadata": {},
    }

    result = validate_lines([json.dumps(event)], require_run_id=True)

    assert result["valid"] is False
    assert "no origami_api_operation events with run_id found" in result["errors"]


def test_structured_log_validator_cli_reads_stdin() -> None:
    event = {
        "event": "origami_api_operation",
        "action": "run_benchmark",
        "environment": "staging",
        "request_id": "req-456",
        "actor": "dev@example.com",
        "source_ip": "10.0.0.8",
        "method": "POST",
        "path": "/runs/benchmark",
        "status_code": 200,
        "target": None,
        "run_id": "benchmark-123",
        "timestamp": "2026-05-16T18:00:00+00:00",
        "metadata": {"quality_gate_passed": True},
    }

    completed = subprocess.run(
        [sys.executable, "scripts/validate_structured_logs.py", "--require-run-id"],
        input=json.dumps(event),
        text=True,
        capture_output=True,
        check=True,
    )

    assert "Structured log validation passed" in completed.stdout


def test_structured_logging_runbook_is_wired_to_readiness() -> None:
    runbook = Path("docs/structured_logging.md").read_text()
    staging = Path("docs/staging_deployment.md").read_text()
    readiness_zh = Path("PRODUCTION_READINESS.zh.md").read_text()
    readiness_en = Path("PRODUCTION_READINESS.en.md").read_text()

    assert os.access(Path("scripts/validate_structured_logs.py"), os.X_OK)
    assert "request_id" in runbook
    assert "run_id" in runbook
    assert "scripts/validate_structured_logs.py --require-run-id" in runbook
    assert "docs/structured_logging.md" in staging
    assert "- [x] structured logs 包含 request id / run id。" in readiness_zh
    assert "- [x] Structured logs include request id / run id." in readiness_en
