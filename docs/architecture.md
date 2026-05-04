<!-- 中文：架构说明文档，描述平台运行流、目录职责和 MVP 里程碑。 -->
<!-- English: Architecture documentation describing runtime flow, folder responsibilities, and MVP milestones. -->

# Mini PIC 2.0 DevOps Architecture

## Purpose

This repository is structured as a compact DevOps platform around the mini PIC 2.0 learning plan. It is not just a model repo: it gives each experiment a repeatable path from local execution to tests, benchmarks, export, edge mock, observability, and audit verification.

## Runtime Flow

```text
observation
  -> AMDC calibrates sensor drift
  -> STUM estimates uncertainty and alert tier
  -> HTD-IRL selects or refreshes a task plan
  -> GRPO proposes an action
  -> SEOM checks safety rules and may override the action
  -> CRL-MRS adds fleet coordination context
  -> action + events + audit entry
```

## Folder Roles

- `src/origami/core`: shared pipeline runtime, config, registries, artifact handling.
- `src/origami/models`: six PIC 2.0 model modules.
- `src/origami/envs`: simulated robotics and grid environments.
- `src/origami/training`: training entrypoints for policies and predictors.
- `src/origami/evaluation`: smoke, regression, and stress evaluation.
- `src/origami/benchmark`: latency and quality benchmark runners.
- `src/origami/dashboard`: static artifact dashboard assets served by FastAPI.
- `src/origami/export`: ONNX export and validation.
- `src/origami/edge`: local edge deployment mock.
- `src/origami/observability`: logs, metrics, traces, and structured events.
- `src/origami/audit`: SHA-256 audit chain and verification.
- `configs`: reproducible run, benchmark, and observability configuration.
- `artifacts`: generated models, reports, benchmarks, and audit logs.

## MVP Milestones

1. Run a smoke pipeline locally.
2. Add unit tests for six module contracts.
3. Record latency for each stage.
4. Export GRPO and STUM placeholders to ONNX.
5. Serve exported models through edge mock.
6. Verify immutable audit chain after a run.

## Quality Gate

Run the local DevOps quality gate with:

```bash
make quality
```

It runs lint, unit/smoke tests, the Carry & Go scenario suite, latency benchmark, and audit verification. The scenario and benchmark commands write JSON reports to `artifacts/reports/`.

For easier review, the scenario runner also writes:

- `artifacts/reports/scenario_report.md`: compact Markdown table for humans
- `artifacts/events/scenario_events.jsonl`: per-module observability events
- `artifacts/audit/scenario_audit.jsonl`: persisted audit-chain records

## Artifact Dashboard

The dashboard is a local FastAPI-served view over the latest generated artifacts. It does not need a frontend build step.

```bash
make quality
make dashboard
```

Open `http://127.0.0.1:8000/dashboard`.

The dashboard reads:

- `GET /api/reports/scenario`
- `GET /api/reports/benchmark`
- `GET /api/events/scenario`
- `GET /api/audit/scenario`
