<!-- English: Internal launch scope and DevOps launch plan defining v0.1 production readiness boundaries, acceptance criteria, and execution path. -->
<!-- Chinese: See PRODUCTION_READINESS.zh.md for the Chinese version. -->

# Origami Mini PIC 2.0 DevOps Platform Production Readiness

Language: [Chinese](PRODUCTION_READINESS.zh.md) | English

## Launch Scope

### Launch Object

Origami Mini PIC 2.0 DevOps Platform for Carry & Go developers.

### Launch Purpose

Provide Carry & Go developers with an internally accessible simulation validation platform for running the PIC 2.0 pipeline, executing Carry & Go scenario tests, and reviewing benchmark, audit, and observability results without depending on real robots or real sensor data before development work reaches hardware validation.

### Out of Scope for This Launch

1. The platform does not directly control real Carry & Go robots.
2. The platform does not connect to the production robot command chain.
3. The platform does not replace real hardware testing.
4. The platform is not the final model training platform.
5. The platform does not process real user privacy data or customer data.

## v0.1 Success Criteria

v0.1 is successful when the platform can be used as a stable internal developer simulation validation service, not as a safety-critical robot control system.

- Developers can access the Dashboard and API through the internal network.
- Developers can run smoke, scenario suite, multi-step scenario, benchmark, and audit verification workflows.
- The Dashboard can display scenario, benchmark, audit, run history, and observability results.
- Each platform-triggered run has run history, an artifact snapshot, and audit records.
- CI quality gates remain green before release: lint, unit/smoke tests, scenario suite, benchmark, and audit verification.
- Run data only comes from simulated scenarios, test configuration, or developer-authored manual input.
- Platform failures do not affect real robots, the production command chain, customer data, or privacy data.
- The service can be rolled back to the previous known-good version.

## Risk Boundaries

| Area | v0.1 Decision |
| --- | --- |
| Robot control | Connecting to real robot control chains is forbidden. |
| Sensor input | Only simulation, fixtures, YAML scenarios, and developer-authored manual input are allowed. |
| User data | Importing real user privacy data or customer data is forbidden. |
| Model training | The platform is for pre-development validation only, not final model training. |
| Safety conclusions | Scenario test results are developer signals only and do not replace hardware testing or safety certification. |
| External access | Access is limited to internal networks or controlled VPN. |

## DevOps Launch Plan

### Phase 0: Freeze Launch Boundaries, 1 Day

Goal: make sure the team shares one definition of what v0.1 can and cannot do.

Work items:

- Review the launch scope and non-goals in this document.
- Confirm the v0.1 users: Carry & Go developers.
- Review Dashboard/API wording so it does not imply the platform can control real robots.
- Create a v0.1 launch epic in the issue tracker and split the following phases into trackable work items.

Acceptance criteria:

- This document is accepted by the project owner.
- Every v0.1 task maps back to this launch scope.

### Phase 1: Service Boundaries and Access Security, 3-5 Days

Goal: make the platform safe to expose to internal developers.

Work items:

- Add minimal API authentication, prioritizing `/runs/*`, `/api/scenarios/*`, `/api/history/*`, `/api/audit/*`, and `/api/reports/*`.
- Read API token, artifact root, Grafana URL, environment name, and log level from environment variables.
- Add CORS/host policy so only internal domains or the internal gateway can access the service.
- Define health and metrics access separately so Prometheus can still scrape metrics.
- Record actor, request id, run id, timestamp, and source IP for critical operations.

Acceptance criteria:

- Unauthenticated requests cannot trigger runs, modify scenarios, or read audit/history/report data.
- Prometheus can still scrape `/metrics`.
- Local development mode and internal deployment mode both have clear startup paths.

### Phase 2: Production Image and Deployment Configuration, 3-5 Days

Goal: move from local development compose to a deployable service.

Work items:

- Convert the Dockerfile into a production image: pinned base image, non-root user, no source mount dependency, and locked dependency installation.
- Keep `docker-compose.yml` for local development, and add production deployment configuration such as `docker-compose.prod.yml` or an environment-specific deployment template.
- Pin Prometheus and Grafana image versions instead of using `latest`.
- Disable production Grafana anonymous admin and use internal SSO, reverse proxy authentication, or a controlled read-only account.
- Configure persistent volumes for artifacts, run history, audit, Prometheus data, and Grafana data.
- Add resource limits, restart policy, healthchecks, and read-only mounts where appropriate.

Acceptance criteria:

- The production image can start without mounting the project source tree.
- `api`, `prometheus`, and `grafana` all use pinned versions and health checks.
- Artifacts, history, and audit data survive deployment restarts.

### Phase 3: Runtime Reliability and Data Persistence, 1 Week

Goal: make runs reliable and traceable for multiple internal users without overwriting each other.

Work items:

- Assign a unique run id to every scenario, multi-step scenario, and benchmark run.
- Write each run to an isolated artifact directory, then update a latest report pointer or index.
- Add a file lock or task queue to prevent concurrent runs from writing the same report, audit, or event files.
- Upgrade audit/history from a latest-file view into a stable index. SQLite or append-only JSONL is acceptable for v0.1.
- Add an artifact retention policy, such as keeping the last 30 days or the last 500 runs.
- Write Dashboard custom scenarios to a persistent artifact/config directory while keeping image-bundled `configs/scenarios` read-only.
- Add structured error responses and input schemas to reduce invalid runs caused by loose `dict[str, Any]` payloads.

Acceptance criteria:

- Two developers triggering runs at the same time do not overwrite each other's results.
- Any historical run can be traced from Dashboard/API to its input, output, events, and audit records.
- Old artifacts have a cleanup policy and do not grow without bound.

### Phase 4: CI/CD and Release Control, 1 Week

Goal: make every version buildable, scannable, deployable, and rollback-capable.

Work items:

- Consolidate GitHub Actions into one authoritative quality gate.
- Build the production image in CI.
- Add dependency vulnerability scanning, image scanning, and basic SBOM output.
- Run a staging smoke check after the main branch merges.
- Require manual approval through the `internal-production` environment for tags or releases.
- Record version number, git SHA, image digest / image ID, migration notes, and rollback command for each release.

Acceptance criteria:

- Staging deploys automatically and runs smoke/health checks.
- Production deployment requires manual approval.
- Any release can be rolled back to the previous known-good version within 15 minutes.

### Phase 5: Observability and Operations Response, 3-5 Days

Goal: make post-launch issues visible, diagnosable, and actionable.

Work items:

- Define v0.1 SLOs: API availability, run success rate, scenario pass rate, benchmark quality gate, audit validity, and API p95 latency.
- Route Prometheus alerts to Slack, Email, or the team's existing alert channel.
- Add JSON structured logs and propagate request id / run id through the service.
- Write runbooks for common failures: API down, quality gate failed, artifact volume full, Grafana unavailable, and audit verification failed.
- Back up artifacts/history/audit and rehearse recovery.

Acceptance criteria:

- Critical alerts reach the responsible team channel.
- When a quality gate fails, developers can see the failure reason in the Dashboard and locate the artifact.
- Operators can use the runbook to restart, roll back, clean up, and recover the service.

### Phase 6: Internal Trial and v0.1 Release, 1 Week

Goal: validate real developer workflows in a small rollout, then open the platform to Carry & Go developers.

Work items:

- Run the staging environment continuously for 5 business days.
- Run smoke, scenario suite, multi-step scenario, benchmark, and audit verification every day.
- Invite 2-3 Carry & Go developers to try the Dashboard and scenario builder.
- Track trial bugs, misleading wording, performance issues, and workflow gaps.
- Complete the v0.1 release checklist and deploy to internal production.
- Watch the release for 48 hours, then expand access if no blockers appear.

Acceptance criteria:

- No P0/P1 blockers occur during the trial.
- Quality gates pass continuously.
- At least 2 target developers complete a scenario or benchmark workflow.
- v0.1 release notes, rollback plan, and runbook are archived.

## v0.1 Launch Checklist

### Scope

- [x] Launch object is limited to Carry & Go developers.
- [x] Platform purpose is limited to internal simulation validation.
- [x] The platform explicitly does not connect to real robot control chains.
- [x] The platform explicitly does not process real customer data or privacy data.

### Security

- [x] API/Dashboard write operations are authenticated.
- [x] Report, audit, and history read policy is defined.
- [x] Production Grafana does not use anonymous admin.
- [x] Google Workspace SSO reverse-proxy template is available: oauth2-proxy + Nginx.
- [x] API can require trusted proxy-injected user identity headers.
- [ ] Google OAuth client, company domain, and optional Google Group policy are configured in the real environment.
- [ ] Production access is limited to internal networks or VPN.
- [x] Critical operations record actor and request id.

### Deployment

- [x] Production image does not depend on source mounts.
- [x] Containers run as a non-root user.
- [x] Image versions are pinned and do not use floating tags.
- [x] Production compose/chart is separated from development compose.
- [x] Artifacts/history/audit use persistent volumes.

### Reliability

- [x] Every run has a unique run id.
- [x] Concurrent runs do not overwrite artifacts.
- [x] Historical runs can trace input, output, events, and audit.
- [x] Artifact retention policy is enabled.
- [x] Dashboard custom scenarios persist in a writable config directory without modifying bundled scenarios.
- [ ] Rollback flow is verified.

### Quality

- [x] `make quality` passes.
- [x] Scenario suite passes.
- [x] Multi-step scenario suite passes.
- [x] Benchmark quality gate passes.
- [x] Audit verification passes.
- [x] Local production-compose smoke check passes: API healthy, custom scenario create and run.
- [x] CI release gate includes staging smoke check.
- [x] CI release gate includes production image build, dependency scan, image scan, and SBOM.
- [x] Tag releases are bound to the internal-production manual approval environment.
- [x] Release manifest records version, git SHA, image identifier, migration notes, and rollback command.
- [ ] Real staging environment smoke check passes.

### Operations

- [ ] Prometheus scrapes API metrics.
- [ ] Grafana dashboard is accessible.
- [ ] Critical alerts reach the team channel.
- [ ] Structured logs include request id / run id.
- [ ] Runbook is complete and rehearsed.
- [x] Artifacts/history/audit backup and recovery notes exist.

## Recommended Release Cadence

| Period | Goal | Main Deliverables |
| --- | --- | --- |
| Week 1 | Security boundary and deployment foundation | Authentication, environment config, production Docker/Compose, scope document |
| Week 2 | Runtime reliability | Run id, concurrency protection, persistence, retention, input schema |
| Week 3 | CI/CD and operations | Image build, scanning, staging deploy, alerts, runbook |
| Week 4 | Trial and release | Internal trial, bug fixes, release checklist, v0.1 launch |

## Current Launch Assessment

Under the v0.1 scope defined in this document, the project already has the core shape of an internal developer simulation validation platform: pipeline, scenario suite, multi-step runner, benchmark, audit, Dashboard, Prometheus/Grafana configuration, and CI quality gates are already present.

The remaining risks are not around robot safety control. They are around internal service productionization: authentication, production image, persistence, concurrency safety, release pipeline, alerting, and operations process. After the phases above are complete, v0.1 can be positioned as an internal production-ready developer validation platform.
