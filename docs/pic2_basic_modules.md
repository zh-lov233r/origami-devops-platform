<!-- 中文：PIC 2.0 六个基础模块的当前实现说明与后续改进路线。 -->
<!-- English: Current implementation notes and improvement roadmap for the six basic PIC 2.0 modules. -->

# PIC 2.0 Basic Modules

This scaffold now has functional first-pass versions of all six PIC 2.0 modules. They are deliberately lightweight, deterministic, and explainable so they can act as a testing harness before replacing pieces with trained models.

## Current Version

| Module | Basic Behavior |
| --- | --- |
| AMDC | Tracks generic sensor bias and Carry & Go drift: floor friction, elevator timing, camera/depth quality, IMU vibration, and payload scale. |
| STUM | Fuses AMDC residuals, perception/localization uncertainty, sensor freshness, and model disagreement into `LOW`, `MEDIUM`, or `HIGH` gates. |
| HTD-IRL | Builds a three-level Carry & Go task graph, tracks subtask status/progress, emits candidate actions, and records re-plan reasons/recovery actions. |
| GRPO | Expands Carry & Go candidate actions, scores reward breakdowns with rollout value and risk penalties, normalizes group-relative advantages, and selects the best action. |
| SEOM | Enforces Carry & Go safety rules with structured rule details, safety score, SEOM penalty, gradient mask, override action, and audit record. |
| CRL-MRS | Coordinates fleet actions with corridor/elevator/dock resource requests, priority arbitration, conflict graphs, reservations, and cooperative meta-reward. |

## Next Improvements

1. Replace heuristic AMDC correction with per-sensor calibration models and fleet-shared calibration profiles for floor, elevator, camera, IMU, and payload stations.
2. Train a real STUM ensemble and replace the current lightweight ECE/conformal helpers with MAPIE-backed calibration reports.
3. Represent HTD-IRL task graphs with NetworkX, persist task-state transitions, and add measured re-plan latency.
4. Replace GRPO's deterministic rollout heuristic with learned trajectory sampling, offline preference datasets, and policy-gradient updates.
5. Split SEOM rules into configurable vertical profiles such as warehouse, hotel, office, and hospital delivery, then persist SEOM audit records into the platform audit chain.
6. Expand CRL-MRS into a multi-agent simulator with deadlock, elevator contention, charging, reservation fairness, and priority delivery metrics.
7. Persist audit entries to JSONL or SQLite instead of keeping them only in memory.
8. Export GRPO/STUM models to ONNX and benchmark PyTorch vs ONNX Runtime.
