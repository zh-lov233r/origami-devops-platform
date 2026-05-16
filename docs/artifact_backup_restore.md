<!-- 中文：Artifact 备份和恢复 runbook，覆盖 artifacts/history/audit 的 v0.1 运维流程。 -->
<!-- English: Artifact backup and restore runbook covering the v0.1 operations flow for artifacts, history, and audit data. -->

# Artifact Backup And Restore

This runbook covers the v0.1 local-volume artifact store used by the API and
Dashboard. It protects generated reports, event logs, audit logs, run history,
per-run bundles, per-user scenarios, and custom scenario configs.

## Scope

Back up the full `ORIGAMI_ARTIFACT_ROOT`, usually `/var/lib/origami/artifacts`
in production compose. The important subtrees are:

- `reports/`, `events/`, and `audit/`: latest Dashboard views.
- `history/`: run history indexes.
- `runs/`: immutable run bundles with report snapshots.
- `users/`: per-user scenarios, reports, audit, events, and history.
- `configs/scenarios/`: shared custom scenario configs when trusted actor
  identity is not active.

The backup script excludes `.locks/` directories and `backups/` so local lock
files and nested archives are not captured.

## Backup

For staging or production compose, run from the deployment checkout:

```bash
ORIGAMI_ARTIFACT_ROOT=/var/lib/origami/artifacts \
ORIGAMI_BACKUP_DIR=/var/lib/origami/backups \
scripts/artifact_backup.sh
```

The script writes:

- `origami-artifacts-<timestamp>.tar.gz`
- `origami-artifacts-<timestamp>.manifest.json`

Keep the archive and manifest together in the approved internal backup location.
The manifest records the source root, archive path, byte size, creation time,
and SHA-256 checksum.

For v0.1, a daily backup is enough before the pilot widens beyond the first
Carry & Go developer group. Take an extra manual backup before rollback,
retention-policy changes, or any restore rehearsal.

## Restore Rehearsal

Practice restore into an empty directory before touching staging data:

```bash
ORIGAMI_ARTIFACT_ROOT=/tmp/origami-restore-check \
scripts/artifact_restore.sh /var/lib/origami/backups/origami-artifacts-<timestamp>.tar.gz
```

Then validate:

```bash
find /tmp/origami-restore-check -maxdepth 2 -type f | sort | head
```

If you have the manifest checksum, verify it during restore:

```bash
ORIGAMI_ARTIFACT_ROOT=/tmp/origami-restore-check \
ORIGAMI_RESTORE_SHA256=<sha256-from-manifest> \
scripts/artifact_restore.sh /var/lib/origami/backups/origami-artifacts-<timestamp>.tar.gz
```

## Staging Or Production Restore

Stop API writes before restoring:

```bash
docker compose --env-file .env.staging -f docker-compose.prod.yml -f docker-compose.sso.yml stop api
```

Restore refuses to write into a non-empty artifact root by default. To restore
over an existing root, set `ORIGAMI_RESTORE_ALLOW_DIRTY=true`; the script moves
the current root aside as `<artifact-root>.pre-restore-<timestamp>` before
extracting the archive.

```bash
ORIGAMI_ARTIFACT_ROOT=/var/lib/origami/artifacts \
ORIGAMI_RESTORE_ALLOW_DIRTY=true \
ORIGAMI_RESTORE_SHA256=<sha256-from-manifest> \
scripts/artifact_restore.sh /var/lib/origami/backups/origami-artifacts-<timestamp>.tar.gz
```

Restart and verify:

```bash
docker compose --env-file .env.staging -f docker-compose.prod.yml -f docker-compose.sso.yml up -d api
scripts/staging_sso_smoke.sh
```

Manual acceptance after restore:

- Dashboard loads through SSO.
- Existing user-owned custom scenarios are visible only to the same user.
- Run history opens at least one restored run detail.
- Scenario, benchmark, audit, and event latest views are available.
- Prometheus and Grafana still load after the API is healthy.

## Ownership

Assign one restore owner for each internal environment. The owner should keep
the backup location, retention period, restore command, latest rehearsal date,
and last successful smoke-check result in the release notes or environment
runbook.
