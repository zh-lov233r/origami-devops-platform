#!/usr/bin/env bash
# 中文：从 Origami artifact 备份恢复到 artifact root，默认拒绝覆盖已有数据。
# English: Restore an Origami artifact backup into the artifact root, refusing to overwrite existing data by default.

set -euo pipefail

archive="${1:-${ORIGAMI_RESTORE_ARCHIVE:-}}"
artifact_root="${ORIGAMI_ARTIFACT_ROOT:-artifacts}"
allow_dirty="${ORIGAMI_RESTORE_ALLOW_DIRTY:-false}"
expected_sha="${ORIGAMI_RESTORE_SHA256:-}"
timestamp="${ORIGAMI_RESTORE_TIMESTAMP:-$(date -u +%Y%m%dT%H%M%SZ)}"
python_bin="${PYTHON:-python3}"

fail() {
  echo "Artifact restore failed: $*" >&2
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

resolve_path() {
  "${python_bin}" -c 'from pathlib import Path; import sys; print(Path(sys.argv[1]).expanduser().resolve())' "$1"
}

if [ -z "${archive}" ]; then
  fail "set ORIGAMI_RESTORE_ARCHIVE or pass the backup archive path as the first argument"
fi

if [ ! -f "${archive}" ]; then
  fail "backup archive not found: ${archive}"
fi

archive_abs="$(resolve_path "${archive}")"
artifact_root_abs="$(resolve_path "${artifact_root}")"

if [ -n "${expected_sha}" ]; then
  actual_sha="$(checksum_file "${archive_abs}")"
  if [ "${actual_sha}" != "${expected_sha}" ]; then
    fail "sha256 mismatch for ${archive_abs}: expected ${expected_sha}, got ${actual_sha}"
  fi
fi

tar -tzf "${archive_abs}" >/dev/null

if [ -d "${artifact_root_abs}" ] && [ -n "$(find "${artifact_root_abs}" -mindepth 1 -maxdepth 1 -print -quit)" ]; then
  if [ "${allow_dirty}" != "true" ]; then
    fail "${artifact_root_abs} is not empty; set ORIGAMI_RESTORE_ALLOW_DIRTY=true to move it aside before restore"
  fi

  case "${archive_abs}" in
    "${artifact_root_abs}"/*)
      temp_archive="${TMPDIR:-/tmp}/$(basename "${archive_abs}").${timestamp}"
      cp "${archive_abs}" "${temp_archive}"
      archive_abs="${temp_archive}"
      ;;
  esac

  snapshot="${artifact_root_abs}.pre-restore-${timestamp}"
  mv "${artifact_root_abs}" "${snapshot}"
  echo "Existing artifact root moved to ${snapshot}"
fi

mkdir -p "${artifact_root_abs}"
tar -xzf "${archive_abs}" -C "${artifact_root_abs}"

echo "Artifact restore completed:"
echo "  archive: ${archive_abs}"
echo "  artifact_root: ${artifact_root_abs}"
