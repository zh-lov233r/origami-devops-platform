#!/usr/bin/env python3
"""
中文：运行 staging 验收自动化检查，并将自动证据写入 v0.1 验收报告。
English: Run staging acceptance automation and write collected evidence into the v0.1 report.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

try:
    from scripts.write_staging_acceptance_report import build_report, write_report_files
except ModuleNotFoundError:  # pragma: no cover - used when invoked as scripts/run_staging_acceptance.py
    from write_staging_acceptance_report import build_report, write_report_files


CommandRunner = Callable[[Sequence[str], dict[str, str]], subprocess.CompletedProcess[str]]
DEFAULT_OUTPUT_DIR = Path("artifacts/acceptance")


@dataclass
class AcceptanceRunOptions:
    environment: str = "staging"
    base_url: str = ""
    direct_api_url: str = ""
    api_token: str = ""
    image_ref: str = ""
    git_sha: str = ""
    owner: str = ""
    generated_at: str = ""
    output_dir: Path = DEFAULT_OUTPUT_DIR
    skip_sso_smoke: bool = False
    structured_log_file: Path | None = None
    require_log_run_id: bool = True
    run_backup_restore: bool = False
    artifact_root: Path = Path("artifacts")
    backup_dir: Path | None = None
    restore_root: Path | None = None
    status_overrides: dict[str, str] = field(default_factory=dict)
    evidence_overrides: dict[str, str] = field(default_factory=dict)
    note_overrides: dict[str, str] = field(default_factory=dict)
    fail_on_pending: bool = False


def main() -> int:
    options = _parse_args()
    payload = collect_acceptance_report(options)
    json_path, markdown_path = write_report_files(payload, options.output_dir)
    print(f"Staging acceptance report written: {markdown_path}")
    print(f"Staging acceptance JSON written: {json_path}")
    print(f"Overall status: {payload['overall_status']}")

    if payload["overall_status"] in {"fail", "blocked"}:
        return 1
    if options.fail_on_pending and payload["overall_status"] == "pending":
        return 1
    return 0


def collect_acceptance_report(
    options: AcceptanceRunOptions,
    *,
    command_runner: CommandRunner | None = None,
) -> dict[str, Any]:
    runner = command_runner or _run_command
    statuses: dict[str, str] = {}
    evidence: dict[str, str] = {}
    notes: dict[str, str] = {}

    _collect_sso_smoke(options, statuses, evidence, notes, runner)
    _collect_structured_logs(options, statuses, evidence, notes, runner)
    _collect_backup_restore(options, statuses, evidence, notes, runner)

    statuses.update(options.status_overrides)
    evidence.update(options.evidence_overrides)
    notes.update(options.note_overrides)

    return build_report(
        environment=options.environment,
        base_url=options.base_url,
        image_ref=options.image_ref,
        git_sha=options.git_sha,
        owner=options.owner,
        generated_at=options.generated_at or datetime.now(UTC).isoformat(),
        statuses=statuses,
        evidence=evidence,
        notes=notes,
    )


def _collect_sso_smoke(
    options: AcceptanceRunOptions,
    statuses: dict[str, str],
    evidence: dict[str, str],
    notes: dict[str, str],
    runner: CommandRunner,
) -> None:
    if options.skip_sso_smoke:
        notes["sso_smoke"] = "Skipped by --skip-sso-smoke; attach manual evidence before release."
        return

    if not options.base_url:
        statuses["sso_smoke"] = "blocked"
        evidence["sso_smoke"] = "ORIGAMI_STAGING_BASE_URL or --base-url is required."
        return

    env = _base_env(options)
    env["ORIGAMI_STAGING_BASE_URL"] = options.base_url
    if options.direct_api_url:
        env["ORIGAMI_STAGING_DIRECT_API_URL"] = options.direct_api_url
    if options.api_token:
        env["ORIGAMI_API_TOKEN"] = options.api_token

    result = runner(["scripts/staging_sso_smoke.sh"], env)
    statuses["sso_smoke"] = "pass" if result.returncode == 0 else "fail"
    evidence["sso_smoke"] = _command_evidence("scripts/staging_sso_smoke.sh", result)


def _collect_structured_logs(
    options: AcceptanceRunOptions,
    statuses: dict[str, str],
    evidence: dict[str, str],
    notes: dict[str, str],
    runner: CommandRunner,
) -> None:
    if options.structured_log_file is None:
        notes["structured_logs"] = (
            "No --structured-log-file provided; attach docker compose API log evidence manually."
        )
        return

    command = ["scripts/validate_structured_logs.py", str(options.structured_log_file)]
    if options.require_log_run_id:
        command.append("--require-run-id")

    result = runner(command, _base_env(options))
    statuses["structured_logs"] = "pass" if result.returncode == 0 else "fail"
    evidence["structured_logs"] = _command_evidence(" ".join(command), result)


def _collect_backup_restore(
    options: AcceptanceRunOptions,
    statuses: dict[str, str],
    evidence: dict[str, str],
    notes: dict[str, str],
    runner: CommandRunner,
) -> None:
    if not options.run_backup_restore:
        notes["backup_restore"] = (
            "Not run by default; use --run-backup-restore during staging rehearsal."
        )
        return

    if not options.artifact_root.exists():
        statuses["backup_restore"] = "blocked"
        evidence["backup_restore"] = f"Artifact root does not exist: {options.artifact_root}"
        return

    with tempfile.TemporaryDirectory(prefix="origami-acceptance-backup-") as temp_dir:
        backup_dir = options.backup_dir or Path(temp_dir) / "backups"
        backup_env = _base_env(options)
        backup_env["ORIGAMI_ARTIFACT_ROOT"] = str(options.artifact_root)
        backup_env["ORIGAMI_BACKUP_DIR"] = str(backup_dir)
        backup_result = runner(["scripts/artifact_backup.sh"], backup_env)
        if backup_result.returncode != 0:
            statuses["backup_restore"] = "fail"
            evidence["backup_restore"] = _command_evidence("scripts/artifact_backup.sh", backup_result)
            return

        archives = sorted(backup_dir.glob("origami-artifacts-*.tar.gz"))
        if not archives:
            statuses["backup_restore"] = "fail"
            evidence["backup_restore"] = "Backup command completed but no archive was produced."
            return

        restore_root = options.restore_root or Path(temp_dir) / "restore-check"
        restore_env = _base_env(options)
        restore_env["ORIGAMI_ARTIFACT_ROOT"] = str(restore_root)
        restore_env["ORIGAMI_RESTORE_ARCHIVE"] = str(archives[-1])
        restore_result = runner(["scripts/artifact_restore.sh"], restore_env)
        statuses["backup_restore"] = "pass" if restore_result.returncode == 0 else "fail"
        evidence["backup_restore"] = (
            _command_evidence("scripts/artifact_backup.sh", backup_result)
            + "\n"
            + _command_evidence("scripts/artifact_restore.sh", restore_result)
        )


def _run_command(command: Sequence[str], env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, check=False, capture_output=True, text=True, env=env)


def _command_evidence(command: str, result: subprocess.CompletedProcess[str]) -> str:
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if not output:
        output = "no output"
    return f"`{command}` exited {result.returncode}.\n{_truncate(output)}"


def _truncate(value: str, limit: int = 1200) -> str:
    return value if len(value) <= limit else value[:limit].rstrip() + "\n... truncated ..."


def _base_env(options: AcceptanceRunOptions) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHON", os.environ.get("PYTHON", ".venv/bin/python"))
    if options.environment:
        env["ORIGAMI_ENV"] = options.environment
    return env


def _parse_args() -> AcceptanceRunOptions:
    parser = argparse.ArgumentParser(description="Run staging acceptance checks and write a report.")
    parser.add_argument("--environment", default=os.environ.get("ORIGAMI_ENV", "staging"))
    parser.add_argument("--base-url", default=os.environ.get("ORIGAMI_STAGING_BASE_URL", ""))
    parser.add_argument(
        "--direct-api-url",
        default=os.environ.get("ORIGAMI_STAGING_DIRECT_API_URL", ""),
    )
    parser.add_argument("--api-token", default=os.environ.get("ORIGAMI_API_TOKEN", ""))
    parser.add_argument("--image-ref", default=os.environ.get("ORIGAMI_API_IMAGE", ""))
    parser.add_argument("--git-sha", default=os.environ.get("GITHUB_SHA", _git_sha()))
    parser.add_argument("--owner", default=os.environ.get("ORIGAMI_ACCEPTANCE_OWNER", ""))
    parser.add_argument("--generated-at", default="")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--skip-sso-smoke", action="store_true")
    parser.add_argument("--structured-log-file", type=Path)
    parser.add_argument("--no-require-log-run-id", action="store_true")
    parser.add_argument("--run-backup-restore", action="store_true")
    parser.add_argument("--artifact-root", type=Path, default=Path("artifacts"))
    parser.add_argument("--backup-dir", type=Path)
    parser.add_argument("--restore-root", type=Path)
    parser.add_argument("--fail-on-pending", action="store_true")
    parser.add_argument("--status", action="append", default=[])
    parser.add_argument("--evidence", action="append", default=[])
    parser.add_argument("--note", action="append", default=[])
    args = parser.parse_args()
    return AcceptanceRunOptions(
        environment=args.environment,
        base_url=args.base_url,
        direct_api_url=args.direct_api_url,
        api_token=args.api_token,
        image_ref=args.image_ref,
        git_sha=args.git_sha,
        owner=args.owner,
        generated_at=args.generated_at,
        output_dir=args.output_dir,
        skip_sso_smoke=args.skip_sso_smoke,
        structured_log_file=args.structured_log_file,
        require_log_run_id=not args.no_require_log_run_id,
        run_backup_restore=args.run_backup_restore,
        artifact_root=args.artifact_root,
        backup_dir=args.backup_dir,
        restore_root=args.restore_root,
        status_overrides=_parse_key_values(args.status, default_value="pass"),
        evidence_overrides=_parse_key_values(args.evidence, default_value=""),
        note_overrides=_parse_key_values(args.note, default_value=""),
        fail_on_pending=args.fail_on_pending,
    )


def _parse_key_values(values: list[str], default_value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        key, separator, raw_value = value.partition("=")
        if not separator:
            parsed[value] = default_value
            continue
        parsed[key.strip()] = raw_value.strip()
    return {key: value for key, value in parsed.items() if key}


def _git_sha() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


if __name__ == "__main__":
    raise SystemExit(main())
