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
PYTHONPATH=src python3 -m origami.cli.main edge-mock
PYTHONPATH=src python3 -m origami.cli.main audit-verify
```

Run the dashboard after generating scenario and benchmark artifacts:

```bash
make quality
make dashboard
```

Open `http://127.0.0.1:8000/dashboard`.

## Target Workflow

```text
config -> run pipeline -> collect events -> benchmark latency
       -> export model -> edge deployment mock -> audit verification
```

## Architecture

See [docs/architecture.md](docs/architecture.md).
