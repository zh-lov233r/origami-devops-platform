"""
中文：Release workflow 单元测试，防止 Phase 4 CI/CD 门禁退化。
English: Unit tests for the release workflow to prevent Phase 4 CI/CD gate regressions.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import yaml


WORKFLOW_PATH = Path(".github/workflows/quality.yml")


def _workflow() -> dict:
    return yaml.load(WORKFLOW_PATH.read_text(), Loader=yaml.BaseLoader)


def test_release_gate_is_the_single_authoritative_workflow() -> None:
    workflow = _workflow()

    assert WORKFLOW_PATH.exists()
    assert not Path(".github/workflows/ci.yml").exists()
    assert workflow["name"] == "release-gate"
    assert workflow["on"]["push"]["branches"] == ["main"]
    assert workflow["on"]["push"]["tags"] == ["v*"]


def test_release_gate_contains_phase4_jobs() -> None:
    jobs = _workflow()["jobs"]

    assert {
        "workflow-lint",
        "quality",
        "dependency-scan",
        "production-image",
        "sso-dry-run",
        "staging-smoke",
        "internal-production-approval",
    } <= set(jobs)
    assert jobs["sso-dry-run"]["needs"] == ["production-image"]
    assert jobs["staging-smoke"]["needs"] == ["production-image", "sso-dry-run"]
    assert jobs["staging-smoke"]["environment"]["name"] == "staging"
    assert jobs["internal-production-approval"]["needs"] == [
        "production-image",
        "sso-dry-run",
    ]
    assert jobs["internal-production-approval"]["environment"]["name"] == "internal-production"


def test_release_gate_runs_quality_scans_image_build_and_smoke() -> None:
    workflow_text = WORKFLOW_PATH.read_text()

    assert "make quality PYTHON=.venv/bin/python" in workflow_text
    assert "make multistep-scenario PYTHON=.venv/bin/python" in workflow_text
    assert "pip-audit" in workflow_text
    assert "docker build --pull" in workflow_text
    assert "aquasec/trivy:0.58.2" in workflow_text
    assert "--scanners vuln --ignore-unfixed" in workflow_text
    assert "image-sbom.cdx.json" in workflow_text
    assert "trivy-image.sarif" in workflow_text
    assert "scripts/staging_smoke.sh" in workflow_text
    assert "scripts/sso_dry_run_smoke.sh" in workflow_text
    assert "scripts/write_release_manifest.sh" in workflow_text


def test_release_scripts_are_executable_and_manifest_records_release_metadata(
    tmp_path: Path,
) -> None:
    manifest_script = Path.cwd() / "scripts/write_release_manifest.sh"
    smoke_script = Path.cwd() / "scripts/staging_smoke.sh"
    sso_dry_run_script = Path.cwd() / "scripts/sso_dry_run_smoke.sh"
    staging_preflight_script = Path.cwd() / "scripts/staging_host_preflight.sh"
    staging_sso_script = Path.cwd() / "scripts/staging_sso_smoke.sh"

    assert os.access(manifest_script, os.X_OK)
    assert os.access(smoke_script, os.X_OK)
    assert os.access(sso_dry_run_script, os.X_OK)
    assert os.access(staging_preflight_script, os.X_OK)
    assert os.access(staging_sso_script, os.X_OK)

    subprocess.run(
        [
            str(manifest_script),
            "v0.1.0",
            "abc123",
            "ghcr.io/example/origami-api:abc123",
            "sha256:test",
            "No migrations.",
            "docker compose up -d api",
        ],
        cwd=tmp_path,
        check=True,
    )

    manifest = (tmp_path / "artifacts/release/release-manifest.md").read_text()

    assert "Version: `v0.1.0`" in manifest
    assert "Git SHA: `abc123`" in manifest
    assert "Image: `ghcr.io/example/origami-api:abc123`" in manifest
    assert "Image digest: `sha256:test`" in manifest
    assert "No migrations." in manifest
    assert "docker compose up -d api" in manifest
