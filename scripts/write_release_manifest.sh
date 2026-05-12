#!/usr/bin/env bash
# 中文：生成 release manifest，记录版本、SHA、镜像标识、迁移说明和回滚命令。
# English: Generate a release manifest with version, SHA, image identifier, migration notes, and rollback command.

set -euo pipefail

version="${1:?version is required}"
git_sha="${2:?git sha is required}"
image_ref="${3:?image ref is required}"
image_digest="${4:?image digest is required}"
migration_notes="${5:?migration notes are required}"
rollback_command="${6:?rollback command is required}"

mkdir -p artifacts/release

cat > artifacts/release/release-manifest.md <<MANIFEST
# Origami Release Manifest

- Version: \`${version}\`
- Git SHA: \`${git_sha}\`
- Image: \`${image_ref}\`
- Image digest: \`${image_digest}\`
- Generated at UTC: \`$(date -u +%Y-%m-%dT%H:%M:%SZ)\`

## Migration Notes

${migration_notes}

## Rollback Command

\`\`\`bash
${rollback_command}
\`\`\`
MANIFEST
