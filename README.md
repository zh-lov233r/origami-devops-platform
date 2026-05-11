<!-- 中文：项目入口说明，介绍 mini PIC 2.0 DevOps 平台的目标、快速启动命令和架构入口。 -->
<!-- English: Project entrypoint documentation describing the mini PIC 2.0 DevOps platform, quick-start commands, and architecture links. -->

# Origami Mini PIC 2.0 DevOps Platform

Local-first DevOps scaffold for a mini PIC 2.0 platform. The goal is to make robot intelligence experiments reproducible from a single workspace: run a pipeline, test it, benchmark latency, export models, mock edge deployment, and verify an audit trail.

## What This Contains

- A six-stage `PIC2Pipeline` skeleton: AMDC, STUM, HTD-IRL, GRPO, SEOM, CRL-MRS.
- A small CLI with smoke run, benchmark, export mock, edge mock, and audit verification commands.
- A FastAPI artifact dashboard for scenario, benchmark, observability, and audit reports.
- Config folders for pipeline, benchmark, and observability settings.
- Stable locations for model code, environments, training, evaluation, exports, edge runtime, observability, and audit artifacts.

## Quick Start

```bash
PYTHONPATH=src python3 -m origami.cli.main smoke
PYTHONPATH=src python3 -m origami.cli.main benchmark
PYTHONPATH=src python3 -m origami.cli.main multistep-scenario
PYTHONPATH=src python3 -m origami.cli.main edge-mock
PYTHONPATH=src python3 -m origami.cli.main audit-verify
```

The `multistep-scenario` command includes long-running timeline cases with repeated
pipeline ticks, simulated battery drain, and mid-route interruption/recovery checks.

Run the dashboard after generating scenario and benchmark artifacts:

```bash
make quality
make dashboard
```

Open `http://127.0.0.1:8000/dashboard`. The dashboard can build custom scenarios, refresh artifacts, trigger scenario, multi-step timeline, or benchmark runs, show run history, and open the provisioned Grafana observability dashboard in a new tab.

For an internal deployment-style local run, require an API token for report, audit, history,
scenario, benchmark, and run endpoints:

```bash
ORIGAMI_AUTH_REQUIRED=true ORIGAMI_API_TOKEN=dev-token make dashboard
```

Enter the same token in the Dashboard API Token field. Health checks stay public by default,
and `/metrics` stays public unless `ORIGAMI_METRICS_AUTH_REQUIRED=true` is set.
Internal deployments can also set `ORIGAMI_ALLOWED_ORIGINS`,
`ORIGAMI_TRUSTED_HOSTS`, and `ORIGAMI_ACTOR_HEADER` to restrict browser origins,
validate host headers, and record the upstream developer identity in structured operation logs.

Run the local observability stack:

```bash
make observability
```

The API service uses a local Docker image with Python runtime dependencies preinstalled, so
dependencies are downloaded during the first image build instead of every `docker compose up`.
Your source tree is mounted into the container, so normal code changes do not require package
reinstallation. Rebuild the API image only after dependency changes in `pyproject.toml`:

```bash
make observability-build
```

Prometheus will scrape the API at `http://api:8000/metrics` from inside Docker. Open `http://127.0.0.1:9090` for the Prometheus UI, `http://127.0.0.1:3000/d/origami-overview` for the provisioned Grafana dashboard, or hit `http://127.0.0.1:8000/metrics` directly for the API metrics payload.

The Prometheus stack also loads local alert rules for API availability, 5xx errors, p95 latency, scenario gate failures, benchmark gate failures, pass-rate drops, and module latency regressions. Open `http://127.0.0.1:9090/alerts` to inspect active alerts.

## Continuous Integration

GitHub Actions runs the project quality gates on every push and pull request:

```bash
make lint
python -m pytest --junitxml=artifacts/reports/pytest.xml
make scenario
make benchmark
make audit-verify
```

The workflow uploads `artifacts/reports`, `artifacts/events`, and `artifacts/audit` so failed runs keep the scenario report, benchmark report, pytest XML, event log, and audit log attached to the CI run.

## Target Workflow

```text
config -> run pipeline -> collect events -> benchmark latency
       -> export model -> edge deployment mock -> audit verification
```

## Architecture

See [docs/architecture.md](docs/architecture.md).

## Production Readiness

See [PRODUCTION_READINESS.zh.md](PRODUCTION_READINESS.zh.md) or
[PRODUCTION_READINESS.en.md](PRODUCTION_READINESS.en.md) for the internal v0.1 launch
scope, non-goals, DevOps rollout plan, and production readiness checklist.
