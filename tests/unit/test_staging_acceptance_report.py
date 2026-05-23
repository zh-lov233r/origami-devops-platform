"""
中文：真实 staging 验收报告生成器测试，确保 v0.1 验收项、证据和文档入口不退化。
English: Tests for the real staging acceptance report generator and its v0.1 evidence wiring.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.write_staging_acceptance_report import build_report, render_markdown


def test_staging_acceptance_report_defaults_to_pending_items() -> None:
    report = build_report(
        environment="staging",
        base_url="https://origami-staging.internal",
        image_ref="ghcr.io/example/origami-api:abc123",
        git_sha="abc123",
        owner="carry-go-devops",
        generated_at="2026-05-20T15:00:00+00:00",
        statuses={},
        evidence={},
        notes={},
    )

    item_ids = {item["id"] for item in report["items"]}

    assert report["overall_status"] == "pending"
    assert report["status_counts"]["pending"] == len(report["items"])
    assert {
        "sso_smoke",
        "browser_login_allowed",
        "browser_login_denied",
        "user_isolation",
        "prometheus_scrape",
        "grafana_access",
        "structured_logs",
        "backup_restore",
        "rollback_rehearsal",
        "runbook_rehearsed",
    } <= item_ids


def test_staging_acceptance_report_records_pass_evidence_and_markdown() -> None:
    report = build_report(
        environment="staging",
        base_url="https://origami-staging.internal",
        image_ref="ghcr.io/example/origami-api:abc123",
        git_sha="abc123",
        owner="carry-go-devops",
        generated_at="2026-05-20T15:00:00+00:00",
        statuses={
            "sso_smoke": "pass",
            "structured_logs": "pass",
            "backup_restore": "pass",
        },
        evidence={
            "sso_smoke": "scripts/staging_sso_smoke.sh passed from VPN",
            "structured_logs": "validate_structured_logs.py --require-run-id passed",
            "backup_restore": "restored reports/events/audit/history/runs/users",
        },
        notes={"backup_restore": "restore rehearsal used /tmp/origami-restore-check"},
    )
    markdown = render_markdown(report)

    assert report["overall_status"] == "pending"
    assert report["status_counts"]["pass"] == 3
    assert "scripts/staging_sso_smoke.sh passed from VPN" in markdown
    assert "restore rehearsal used /tmp/origami-restore-check" in markdown
    assert "Overall status: `pending`" in markdown


def test_staging_acceptance_report_rejects_unknown_or_invalid_status() -> None:
    with pytest.raises(ValueError, match="Unknown acceptance item"):
        build_report(
            environment="staging",
            base_url="",
            image_ref="",
            git_sha="",
            owner="",
            generated_at="2026-05-20T15:00:00+00:00",
            statuses={"nope": "pass"},
            evidence={},
            notes={},
        )

    with pytest.raises(ValueError, match="Invalid status"):
        build_report(
            environment="staging",
            base_url="",
            image_ref="",
            git_sha="",
            owner="",
            generated_at="2026-05-20T15:00:00+00:00",
            statuses={"sso_smoke": "green"},
            evidence={},
            notes={},
        )

    with pytest.raises(ValueError, match="Invalid environment"):
        build_report(
            environment="../prod",
            base_url="",
            image_ref="",
            git_sha="",
            owner="",
            generated_at="2026-05-20T15:00:00+00:00",
            statuses={},
            evidence={},
            notes={},
        )


def test_staging_acceptance_report_cli_writes_json_and_markdown(tmp_path: Path) -> None:
    output_dir = tmp_path / "acceptance"

    subprocess.run(
        [
            sys.executable,
            "scripts/write_staging_acceptance_report.py",
            "--environment",
            "staging",
            "--base-url",
            "https://origami-staging.internal",
            "--image-ref",
            "ghcr.io/example/origami-api:abc123",
            "--git-sha",
            "abc123",
            "--owner",
            "carry-go-devops",
            "--generated-at",
            "2026-05-20T15:00:00+00:00",
            "--output-dir",
            str(output_dir),
            "--status",
            "sso_smoke=pass",
            "--evidence",
            "sso_smoke=staging_sso_smoke passed",
        ],
        check=True,
    )

    json_payload = json.loads((output_dir / "staging-acceptance-staging.json").read_text())
    markdown = (output_dir / "staging-acceptance-staging.md").read_text()

    assert json_payload["base_url"] == "https://origami-staging.internal"
    assert json_payload["status_counts"]["pass"] == 1
    assert "staging_sso_smoke passed" in markdown


def test_staging_acceptance_report_is_documented_and_wired() -> None:
    makefile = Path("Makefile").read_text()
    staging_runbook = Path("docs/staging_deployment.md").read_text()
    readme = Path("README.md").read_text()

    assert os.access(Path("scripts/write_staging_acceptance_report.py"), os.X_OK)
    assert os.access(Path("scripts/run_staging_acceptance.py"), os.X_OK)
    assert "staging-acceptance:" in makefile
    assert "$(PYTHON) scripts/run_staging_acceptance.py $(STAGING_ACCEPTANCE_ARGS)" in makefile
    assert "staging-acceptance-report" in makefile
    assert "scripts/run_staging_acceptance.py" in staging_runbook
    assert "scripts/write_staging_acceptance_report.py" in staging_runbook
    assert "artifacts/acceptance/" in staging_runbook
    assert "make staging-acceptance" in readme
    assert "make staging-acceptance-report" in readme
