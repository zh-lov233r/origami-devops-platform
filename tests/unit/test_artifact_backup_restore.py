"""
中文：Artifact 备份恢复脚本测试，防止 history/audit/run bundle 恢复流程退化。
English: Artifact backup and restore script tests for history, audit, and run bundle recovery.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def test_artifact_backup_and_restore_round_trip(tmp_path: Path) -> None:
    artifact_root = tmp_path / "artifacts"
    backup_dir = tmp_path / "backups"
    restore_root = tmp_path / "restored-artifacts"

    _write_text(artifact_root / "reports/scenario_report.json", '{"ok": true}\n')
    _write_text(artifact_root / "events/scenario_events.jsonl", '{"event": "scenario"}\n')
    _write_text(artifact_root / "audit/scenario_audit.jsonl", '{"valid": true}\n')
    _write_text(artifact_root / "history/runs.jsonl", '{"id": "run-1"}\n')
    _write_text(artifact_root / "runs/run-1/report.json", '{"run_id": "run-1"}\n')
    _write_text(artifact_root / "users/dev/configs/scenarios/custom.yaml", "id: custom\n")
    _write_text(artifact_root / ".locks/ignored.lock", "lock\n")
    _write_text(artifact_root / "backups/nested-backup.tar.gz", "nested\n")

    backup_env = {
        **os.environ,
        "ORIGAMI_ARTIFACT_ROOT": str(artifact_root),
        "ORIGAMI_BACKUP_DIR": str(backup_dir),
        "ORIGAMI_BACKUP_TIMESTAMP": "20260516T000000Z",
        "PYTHON": sys.executable,
    }
    subprocess.run(
        [str(Path.cwd() / "scripts/artifact_backup.sh")],
        env=backup_env,
        check=True,
    )

    archive = backup_dir / "origami-artifacts-20260516T000000Z.tar.gz"
    manifest = backup_dir / "origami-artifacts-20260516T000000Z.manifest.json"
    manifest_payload = json.loads(manifest.read_text())

    assert archive.exists()
    assert manifest_payload["archive"] == str(archive)
    assert manifest_payload["source_root"] == str(artifact_root)
    assert manifest_payload["size_bytes"] > 0
    assert len(manifest_payload["sha256"]) == 64

    restore_env = {
        **os.environ,
        "ORIGAMI_ARTIFACT_ROOT": str(restore_root),
        "ORIGAMI_RESTORE_SHA256": manifest_payload["sha256"],
        "PYTHON": sys.executable,
    }
    subprocess.run(
        [str(Path.cwd() / "scripts/artifact_restore.sh"), str(archive)],
        env=restore_env,
        check=True,
    )

    assert (restore_root / "reports/scenario_report.json").read_text() == '{"ok": true}\n'
    assert (restore_root / "audit/scenario_audit.jsonl").read_text() == '{"valid": true}\n'
    assert (restore_root / "history/runs.jsonl").read_text() == '{"id": "run-1"}\n'
    assert (restore_root / "runs/run-1/report.json").read_text() == '{"run_id": "run-1"}\n'
    assert (restore_root / "users/dev/configs/scenarios/custom.yaml").read_text() == (
        "id: custom\n"
    )
    assert not (restore_root / ".locks").exists()
    assert not (restore_root / "backups").exists()


def test_artifact_backup_restore_is_documented_and_wired() -> None:
    makefile = Path("Makefile").read_text()
    staging_runbook = Path("docs/staging_deployment.md").read_text()
    backup_runbook = Path("docs/artifact_backup_restore.md").read_text()
    readiness_zh = Path("PRODUCTION_READINESS.zh.md").read_text()
    readiness_en = Path("PRODUCTION_READINESS.en.md").read_text()

    assert os.access(Path("scripts/artifact_backup.sh"), os.X_OK)
    assert os.access(Path("scripts/artifact_restore.sh"), os.X_OK)
    assert "artifact-backup" in makefile
    assert "artifact-restore" in makefile
    assert "docs/artifact_backup_restore.md" in staging_runbook
    assert "scripts/artifact_backup.sh" in backup_runbook
    assert "scripts/artifact_restore.sh" in backup_runbook
    assert "ORIGAMI_RESTORE_SHA256" in backup_runbook
    assert "- [x] artifacts/history/audit 有备份恢复说明。" in readiness_zh
    assert "- [x] Artifacts/history/audit backup and recovery notes exist." in readiness_en


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
