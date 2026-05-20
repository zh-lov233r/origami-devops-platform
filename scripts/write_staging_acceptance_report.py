#!/usr/bin/env python3
"""
中文：生成真实 staging v0.1 验收报告，汇总 SSO、用户隔离、observability、日志、备份和回滚证据。
English: Generate the real staging v0.1 acceptance report covering SSO, user isolation, observability, logs, backup, and rollback evidence.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


VALID_STATUSES = {"pending", "pass", "fail", "blocked", "not_applicable"}
DEFAULT_OUTPUT_DIR = Path("artifacts/acceptance")


@dataclass(frozen=True)
class AcceptanceItem:
    id: str
    title: str
    category: str
    readiness_ref: str
    command_or_check: str
    acceptance: str


ACCEPTANCE_ITEMS = [
    AcceptanceItem(
        id="oauth_client_configured",
        title="Google OAuth client and allowlist configured",
        category="security",
        readiness_ref="Security: Google OAuth client, company domain, and optional Group policy",
        command_or_check="Complete docs/staging_google_oauth_client.md and run scripts/staging_host_preflight.sh.",
        acceptance="OAuth redirect URI matches staging, placeholder secrets are replaced, and allowlist/domain policy is intentional.",
    ),
    AcceptanceItem(
        id="internal_network_only",
        title="Staging is reachable only through internal network or VPN",
        category="security",
        readiness_ref="Security: production environment allows only internal network or VPN access",
        command_or_check="Confirm external access is blocked and ORIGAMI_SSO_BIND/TLS ingress are internal-only.",
        acceptance="Dashboard/API are reachable from approved internal paths and unavailable from an unapproved external path.",
    ),
    AcceptanceItem(
        id="sso_smoke",
        title="Real staging SSO smoke check passes",
        category="quality",
        readiness_ref="Quality: real staging SSO smoke check",
        command_or_check="ORIGAMI_STAGING_BASE_URL=https://origami-staging.internal scripts/staging_sso_smoke.sh",
        acceptance="Health is reachable, protected routes redirect to oauth2-proxy, Google OAuth starts, and direct token-only access is rejected or network-blocked.",
    ),
    AcceptanceItem(
        id="browser_login_allowed",
        title="Allowlisted browser login succeeds",
        category="quality",
        readiness_ref="Quality: real staging browser login acceptance",
        command_or_check="Open /dashboard in a browser and sign in with the allowlisted staging account.",
        acceptance="The allowlisted account reaches Dashboard after Google login.",
    ),
    AcceptanceItem(
        id="browser_login_denied",
        title="Unallowlisted browser login is denied",
        category="quality",
        readiness_ref="Quality: real staging browser login acceptance",
        command_or_check="Try signing in with an account outside the allowlist/domain policy.",
        acceptance="The unallowlisted account cannot reach Dashboard.",
    ),
    AcceptanceItem(
        id="user_isolation",
        title="User-owned scenarios and history are isolated",
        category="quality",
        readiness_ref="Quality: real staging user isolation acceptance",
        command_or_check="Create a custom scenario as one user and inspect Dashboard/API as another user.",
        acceptance="The scenario and run history are visible only to the owning user.",
    ),
    AcceptanceItem(
        id="prometheus_scrape",
        title="Prometheus scrapes API metrics",
        category="operations",
        readiness_ref="Operations: Prometheus scrapes API metrics",
        command_or_check="Open Prometheus targets or query up{job=\"origami-api\"}.",
        acceptance="The origami-api target is up and has recent scrape timestamps.",
    ),
    AcceptanceItem(
        id="grafana_access",
        title="Grafana overview dashboard is accessible",
        category="operations",
        readiness_ref="Operations: Grafana dashboard is accessible",
        command_or_check="Open /grafana/ or the configured ORIGAMI_GRAFANA_URL through SSO.",
        acceptance="The Origami overview dashboard loads with current API/scenario/benchmark panels.",
    ),
    AcceptanceItem(
        id="alert_delivery",
        title="Critical alerts reach the team channel",
        category="operations",
        readiness_ref="Operations: critical alerts reach the team channel",
        command_or_check="Trigger or dry-run the configured alert route to Slack, Email, or the team alerting system.",
        acceptance="A test alert is received in the responsible channel with owner and runbook context.",
    ),
    AcceptanceItem(
        id="structured_logs",
        title="Structured logs include request id and run id",
        category="operations",
        readiness_ref="Operations: structured logs include request id / run id",
        command_or_check="docker compose ... logs --no-color --tail=300 api | scripts/validate_structured_logs.py --require-run-id",
        acceptance="Recent API operation logs validate and at least one run operation includes a run_id.",
    ),
    AcceptanceItem(
        id="backup_restore",
        title="Artifact backup and restore rehearsal completed",
        category="operations",
        readiness_ref="Operations: artifacts/history/audit backup and recovery",
        command_or_check="scripts/artifact_backup.sh, then scripts/artifact_restore.sh into a restore-check root.",
        acceptance="A restored artifact root contains reports, events, audit, history, runs, and user configs.",
    ),
    AcceptanceItem(
        id="rollback_rehearsal",
        title="Rollback flow verified",
        category="reliability",
        readiness_ref="Reliability: rollback flow verified",
        command_or_check="Set ORIGAMI_API_IMAGE to the previous green image and redeploy API, then rerun staging smoke.",
        acceptance="The previous image comes up, staging smoke passes, and existing artifacts/user scenarios remain visible.",
    ),
    AcceptanceItem(
        id="runbook_rehearsed",
        title="Runbook rehearsed in real staging",
        category="operations",
        readiness_ref="Operations: runbook rehearsed in real staging",
        command_or_check="Walk through deploy, smoke, logs, backup/restore, and rollback sections in docs/staging_deployment.md.",
        acceptance="The rehearsal owner records date, environment, commands, failures, and final result.",
    ),
]


def main() -> int:
    args = _parse_args()
    statuses = _parse_key_values(args.status, default_value="pass")
    evidence = _parse_key_values(args.evidence, default_value="")
    notes = _parse_key_values(args.note, default_value="")
    payload = build_report(
        environment=args.environment,
        base_url=args.base_url,
        image_ref=args.image_ref,
        git_sha=args.git_sha,
        owner=args.owner,
        generated_at=args.generated_at or datetime.now(UTC).isoformat(),
        statuses=statuses,
        evidence=evidence,
        notes=notes,
    )
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"staging-acceptance-{payload['environment']}.json"
    markdown_path = output_dir / f"staging-acceptance-{payload['environment']}.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    markdown_path.write_text(render_markdown(payload))
    print(f"Staging acceptance report written: {markdown_path}")
    print(f"Staging acceptance JSON written: {json_path}")
    print(f"Overall status: {payload['overall_status']}")
    return 0 if payload["overall_status"] in {"pass", "pending"} else 1


def build_report(
    *,
    environment: str,
    base_url: str,
    image_ref: str,
    git_sha: str,
    owner: str,
    generated_at: str,
    statuses: dict[str, str],
    evidence: dict[str, str],
    notes: dict[str, str],
) -> dict[str, Any]:
    known_ids = {item.id for item in ACCEPTANCE_ITEMS}
    unknown_ids = sorted((set(statuses) | set(evidence) | set(notes)) - known_ids)
    if unknown_ids:
        raise ValueError(f"Unknown acceptance item id(s): {', '.join(unknown_ids)}")

    records = []
    for item in ACCEPTANCE_ITEMS:
        status = statuses.get(item.id, "pending")
        if status not in VALID_STATUSES:
            raise ValueError(
                f"Invalid status for {item.id}: {status}. "
                f"Expected one of {', '.join(sorted(VALID_STATUSES))}."
            )
        records.append(
            {
                "id": item.id,
                "title": item.title,
                "category": item.category,
                "readiness_ref": item.readiness_ref,
                "command_or_check": item.command_or_check,
                "acceptance": item.acceptance,
                "status": status,
                "evidence": evidence.get(item.id, ""),
                "notes": notes.get(item.id, ""),
            }
        )

    status_counts = {
        status: sum(1 for record in records if record["status"] == status)
        for status in sorted(VALID_STATUSES)
    }
    return {
        "environment": environment,
        "base_url": base_url,
        "image_ref": image_ref,
        "git_sha": git_sha,
        "owner": owner,
        "generated_at": generated_at,
        "overall_status": _overall_status(records),
        "status_counts": status_counts,
        "items": records,
    }


def render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Staging Acceptance Report",
        "",
        f"- Environment: `{payload['environment']}`",
        f"- Base URL: `{payload['base_url'] or 'unset'}`",
        f"- Image: `{payload['image_ref'] or 'unset'}`",
        f"- Git SHA: `{payload['git_sha'] or 'unset'}`",
        f"- Owner: `{payload['owner'] or 'unset'}`",
        f"- Generated at: `{payload['generated_at']}`",
        f"- Overall status: `{payload['overall_status']}`",
        "",
        "## Summary",
        "",
    ]
    for status, count in payload["status_counts"].items():
        lines.append(f"- `{status}`: {count}")

    lines.extend(["", "## Checklist", ""])
    for item in payload["items"]:
        lines.extend(
            [
                f"### {item['title']}",
                "",
                f"- ID: `{item['id']}`",
                f"- Category: `{item['category']}`",
                f"- Status: `{item['status']}`",
                f"- Readiness ref: {item['readiness_ref']}",
                f"- Command/check: `{item['command_or_check']}`",
                f"- Acceptance: {item['acceptance']}",
                f"- Evidence: {item['evidence'] or 'pending'}",
                f"- Notes: {item['notes'] or 'none'}",
                "",
            ]
        )
    return "\n".join(lines)


def _overall_status(records: list[dict[str, str]]) -> str:
    statuses = {record["status"] for record in records}
    if "fail" in statuses:
        return "fail"
    if "blocked" in statuses:
        return "blocked"
    if "pending" in statuses:
        return "pending"
    return "pass"


def _parse_key_values(values: list[str], default_value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for value in values:
        key, separator, raw_value = value.partition("=")
        if not separator:
            parsed[value] = default_value
            continue
        parsed[key.strip()] = raw_value.strip()
    return {key: value for key, value in parsed.items() if key}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Write a staging v0.1 acceptance report.")
    parser.add_argument("--environment", default=os.environ.get("ORIGAMI_ENV", "staging"))
    parser.add_argument("--base-url", default=os.environ.get("ORIGAMI_STAGING_BASE_URL", ""))
    parser.add_argument("--image-ref", default=os.environ.get("ORIGAMI_API_IMAGE", ""))
    parser.add_argument("--git-sha", default=os.environ.get("GITHUB_SHA", ""))
    parser.add_argument("--owner", default=os.environ.get("ORIGAMI_ACCEPTANCE_OWNER", ""))
    parser.add_argument("--generated-at", default="")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument(
        "--status",
        action="append",
        default=[],
        help="Set item status as item_id=pass|fail|blocked|pending|not_applicable.",
    )
    parser.add_argument(
        "--evidence",
        action="append",
        default=[],
        help="Attach evidence text as item_id=evidence.",
    )
    parser.add_argument(
        "--note",
        action="append",
        default=[],
        help="Attach note text as item_id=note.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(main())
