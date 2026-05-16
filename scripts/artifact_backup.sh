#!/usr/bin/env bash
# 中文：备份 Origami artifact root，覆盖 reports/events/audit/history/runs/users/configs 等运行状态。
# English: Back up the Origami artifact root including reports, events, audit, history, runs, users, and configs.

set -euo pipefail

artifact_root="${ORIGAMI_ARTIFACT_ROOT:-artifacts}"
backup_dir="${ORIGAMI_BACKUP_DIR:-${artifact_root}/backups}"
timestamp="${ORIGAMI_BACKUP_TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
python_bin="${PYTHON:-python3}"

fail() {
  echo "Artifact backup failed: $*" >&2
  exit 1
}

checksum_file() {
  file_path="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "${file_path}" | awk '{print $1}'
  else
    shasum -a 256 "${file_path}" | awk '{print $1}'
  fi
}

file_size_bytes() {
  file_path="$1"
  if stat -c%s "${file_path}" >/dev/null 2>&1; then
    stat -c%s "${file_path}"
  else
    stat -f%z "${file_path}"
  fi
}

if [ ! -d "${artifact_root}" ]; then
  fail "artifact root does not exist: ${artifact_root}"
fi

mkdir -p "${backup_dir}"

archive="${backup_dir}/origami-artifacts-${timestamp}.tar.gz"
manifest="${backup_dir}/origami-artifacts-${timestamp}.manifest.json"

tar -czf "${archive}" \
  -C "${artifact_root}" \
  --exclude="./backups" \
  --exclude="./.locks" \
  --exclude="*/.locks" \
  .

checksum="$(checksum_file "${archive}")"
size_bytes="$(file_size_bytes "${archive}")"
created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

ORIGAMI_BACKUP_ARCHIVE="${archive}" \
ORIGAMI_BACKUP_MANIFEST="${manifest}" \
ORIGAMI_BACKUP_SHA256="${checksum}" \
ORIGAMI_BACKUP_SIZE_BYTES="${size_bytes}" \
ORIGAMI_BACKUP_CREATED_AT="${created_at}" \
ORIGAMI_BACKUP_SOURCE_ROOT="${artifact_root}" \
"${python_bin}" -c '
import json
import os
from pathlib import Path

manifest_path = Path(os.environ["ORIGAMI_BACKUP_MANIFEST"])
payload = {
    "archive": os.environ["ORIGAMI_BACKUP_ARCHIVE"],
    "created_at": os.environ["ORIGAMI_BACKUP_CREATED_AT"],
    "sha256": os.environ["ORIGAMI_BACKUP_SHA256"],
    "size_bytes": int(os.environ["ORIGAMI_BACKUP_SIZE_BYTES"]),
    "source_root": os.environ["ORIGAMI_BACKUP_SOURCE_ROOT"],
}
manifest_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
'

echo "Artifact backup written:"
echo "  archive: ${archive}"
echo "  manifest: ${manifest}"
echo "  sha256: ${checksum}"
