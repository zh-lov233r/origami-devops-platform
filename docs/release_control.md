<!-- 中文：Phase 4 发布控制说明，记录 CI/CD 门禁、staging smoke、生产审批和回滚要求。 -->
<!-- English: Phase 4 release-control notes for CI/CD gates, staging smoke, production approval, and rollback requirements. -->

# Release Control

The authoritative GitHub Actions workflow is `.github/workflows/quality.yml`,
named `release-gate`. It replaces the older duplicate CI workflow and owns the
v0.1 release path.

## Release Gate

The workflow runs on pull requests, pushes to `main`, tags matching `v*`, and
manual dispatch. It includes:

- workflow lint with `actionlint`
- Python quality gate: lint, tests, scenario, benchmark, audit verification
- multi-step scenario gate
- locked runtime dependency export and `pip-audit`
- production Docker image build
- image SBOM generation
- Trivy image scan for fixable high and critical vulnerability findings
- release manifest artifact with version, git SHA, image identifier, migration notes, and rollback command

The production Dockerfile applies Debian security updates during image build and
removes runtime-unneeded Python packaging tools after dependency installation.
The Trivy gate uses `--ignore-unfixed`, so it fails releases for high/critical
issues with an available fix while still reporting upstream issues that do not
yet have a fixed package version.

## Staging

After a push to `main`, the workflow runs a staging smoke check through the
production compose profile. The smoke script verifies API health, runtime config,
custom scenario creation, and a single scenario run with a passing quality gate.

When real staging infrastructure is available, replace the compose build/start
steps with the internal deployment command and keep `scripts/staging_smoke.sh` as
the post-deploy health check.

## Internal Production

Tags matching `v*` create a production candidate. The
`internal-production-approval` job is bound to the `internal-production`
environment so repository environment protection rules can require manual
approval before the production candidate is accepted.

Before approving a release, verify the uploaded release manifest:

- version
- git SHA
- image reference
- image digest or image ID
- migration notes
- rollback command

## Rollback

Rollback target: the previous approved image tag or SHA.

Expected rollback command shape:

```bash
ORIGAMI_API_IMAGE=<previous-image-ref> docker compose --env-file .env.production -f docker-compose.prod.yml up -d api
```

Rollback is considered successful after `scripts/staging_smoke.sh` or the
equivalent production health check passes against the restored version.
