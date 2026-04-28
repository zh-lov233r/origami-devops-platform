<!-- 中文：PIC 2.0 六个基础模块的当前实现说明与后续改进路线。 -->
<!-- English: Current implementation notes and improvement roadmap for the six basic PIC 2.0 modules. -->

# PIC 2.0 Basic Modules

This scaffold now has functional first-pass versions of all six PIC 2.0 modules. They are deliberately lightweight, deterministic, and explainable so they can act as a testing harness before replacing pieces with trained models.

## Current Version

| Module | Basic Behavior |
| --- | --- |
| AMDC | Tracks sensor bias with EMA, applies thermal drift correction, emits calibration residuals. |
| STUM | Computes spatial and temporal uncertainty, emits `LOW`, `MEDIUM`, or `HIGH` gate plus confidence. |
| HTD-IRL | Builds a three-level Carry & Go delivery task graph and triggers local re-planning. |
| GRPO | Scores candidate actions, normalizes them into group-relative advantages, selects the best action. |
| SEOM | Enforces Carry & Go safety rules such as human distance, speed, payload, battery, privacy, and route safety. |
| CRL-MRS | Adjusts actions for corridor and elevator conflicts and computes cooperative meta-reward. |

## Next Improvements

1. Replace heuristic AMDC correction with per-sensor calibration models and fleet-shared calibration profiles.
2. Train a small STUM ensemble and calibrate uncertainty with MAPIE conformal prediction.
3. Represent HTD-IRL task graphs with NetworkX and add measured re-plan latency.
4. Replace GRPO scoring heuristics with rollout-based trajectory sampling and policy-gradient updates.
5. Split SEOM rules into configurable vertical profiles such as warehouse, hotel, office, and hospital delivery.
6. Expand CRL-MRS into a multi-agent simulator with deadlock, elevator contention, charging, and priority delivery metrics.
7. Persist audit entries to JSONL or SQLite instead of keeping them only in memory.
8. Export GRPO/STUM models to ONNX and benchmark PyTorch vs ONNX Runtime.

