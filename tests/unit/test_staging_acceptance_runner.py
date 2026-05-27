"""
中文：staging 验收自动化入口测试，覆盖自动证据收集、阻塞状态和 CLI 写报告。
English: Tests for staging acceptance automation evidence collection, blocked states, and CLI output.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from scripts.run_staging_acceptance import AcceptanceRunOptions, collect_acceptance_report


def test_staging_acceptance_runner_collects_sso_and_log_evidence(tmp_path: Path) -> None:
    calls: list[list[str]] = []

    def fake_runner(
        command: list[str] | tuple[str, ...],
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        return subprocess.CompletedProcess(command, 0, stdout=f"{command[0]} passed\n", stderr="")

    report = collect_acceptance_report(
        AcceptanceRunOptions(
            environment="staging",
            base_url="https://origami-staging.internal",
            structured_log_file=tmp_path / "api.log",
            generated_at="2026-05-20T15:00:00+00:00",
        ),
        command_runner=fake_runner,
    )
    items = {item["id"]: item for item in report["items"]}

    assert items["sso_smoke"]["status"] == "pass"
    assert items["structured_logs"]["status"] == "pass"
    assert calls == [
        ["scripts/staging_sso_smoke.sh"],
        ["scripts/validate_structured_logs.py", str(tmp_path / "api.log"), "--require-run-id"],
    ]


def test_staging_acceptance_runner_blocks_sso_without_base_url() -> None:
    report = collect_acceptance_report(
        AcceptanceRunOptions(
            environment="staging",
            generated_at="2026-05-20T15:00:00+00:00",
        )
    )
    items = {item["id"]: item for item in report["items"]}

    assert report["overall_status"] == "blocked"
    assert items["sso_smoke"]["status"] == "blocked"
    assert "ORIGAMI_STAGING_BASE_URL" in items["sso_smoke"]["evidence"]


def test_staging_acceptance_runner_can_collect_backup_restore(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    artifact_root.mkdir()
    (artifact_root / "report.txt").write_text("ok\n")
    calls: list[list[str]] = []

    def fake_runner(
        command: list[str] | tuple[str, ...],
        env: dict[str, str],
    ) -> subprocess.CompletedProcess[str]:
        calls.append(list(command))
        if command[0] == "scripts/artifact_backup.sh":
            backup_dir = Path(env["ORIGAMI_BACKUP_DIR"])
            backup_dir.mkdir(parents=True, exist_ok=True)
            (backup_dir / "origami-artifacts-test.tar.gz").write_text("archive\n")
        return subprocess.CompletedProcess(command, 0, stdout=f"{command[0]} passed\n", stderr="")

    report = collect_acceptance_report(
        AcceptanceRunOptions(
            environment="staging",
            skip_sso_smoke=True,
            run_backup_restore=True,
            artifact_root=artifact_root,
            generated_at="2026-05-20T15:00:00+00:00",
        ),
        command_runner=fake_runner,
    )
    items = {item["id"]: item for item in report["items"]}

    assert items["backup_restore"]["status"] == "pass"
    assert calls == [["scripts/artifact_backup.sh"], ["scripts/artifact_restore.sh"]]


def test_staging_acceptance_runner_cli_writes_report(tmp_path: Path) -> None:
    output_dir = tmp_path / "acceptance"

    subprocess.run(
        [
            sys.executable,
            "scripts/run_staging_acceptance.py",
            "--environment",
            "staging",
            "--skip-sso-smoke",
            "--generated-at",
            "2026-05-20T15:00:00+00:00",
            "--output-dir",
            str(output_dir),
            "--status",
            "structured_logs=pass",
            "--evidence",
            "structured_logs=manual log validation passed",
        ],
        check=True,
    )

    json_payload = json.loads((output_dir / "staging-acceptance-staging.json").read_text())
    items = {item["id"]: item for item in json_payload["items"]}

    assert json_payload["overall_status"] == "pending"
    assert items["structured_logs"]["status"] == "pass"
    assert items["structured_logs"]["evidence"] == "manual log validation passed"


def test_staging_acceptance_runner_cli_allows_blocked_report_by_default(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "acceptance"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_staging_acceptance.py",
            "--environment",
            "staging",
            "--generated-at",
            "2026-05-20T15:00:00+00:00",
            "--output-dir",
            str(output_dir),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    json_payload = json.loads((output_dir / "staging-acceptance-staging.json").read_text())

    assert result.returncode == 0
    assert json_payload["overall_status"] == "blocked"
    assert "Overall status: blocked" in result.stdout


def test_staging_acceptance_runner_cli_can_fail_on_blocked_report(
    tmp_path: Path,
) -> None:
    output_dir = tmp_path / "acceptance"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run_staging_acceptance.py",
            "--environment",
            "staging",
            "--generated-at",
            "2026-05-20T15:00:00+00:00",
            "--output-dir",
            str(output_dir),
            "--fail-on-pending",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    json_payload = json.loads((output_dir / "staging-acceptance-staging.json").read_text())

    assert result.returncode == 1
    assert json_payload["overall_status"] == "blocked"
