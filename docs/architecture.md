<!-- 作用：记录 mini PIC 2.0 DevOps 平台的架构分层、运行流和目录职责。 -->

<!-- 中文：说明 mini PIC 2.0 DevOps 平台的整体架构、运行流和目录职责。 -->
<!-- English: Describes the mini PIC 2.0 DevOps platform architecture, runtime flow, and folder responsibilities. -->

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
