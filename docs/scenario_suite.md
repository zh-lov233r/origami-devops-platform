<!-- 中文：Carry & Go 场景测试套件说明，定义最小端到端测试覆盖面。 -->
<!-- English: Carry & Go scenario test suite notes defining minimal end-to-end coverage. -->

# Carry & Go Scenario Suite

The scenario files in `configs/scenarios/` are single-step end-to-end cases for the mini PIC 2.0 pipeline. Each file has:

- `observation`: the raw input to `PIC2Pipeline.step`.
- `expected`: the key signals a future scenario runner should assert.
- `tags`: grouping labels for reports and benchmark slices.

## Scenarios

| Scenario | Main Purpose | Expected Signal |
| --- | --- | --- |
| `normal_delivery` | Baseline route progress with healthy payload, battery, and fleet context. | Final action moves east, SEOM passes, audit remains valid. |
| `human_too_close` | Human-proximity life-safety stop. | Final action holds, `C01_person_stop_300mm`, gradient mask `zero`. |
| `low_battery_return` | Energy-aware replan and dock return. | HTD-IRL emits `battery_abort`; GRPO chooses `return_to_dock`. |
| `payload_overweight` | AMDC payload calibration feeding planning and safety. | AMDC marks payload risk; final action holds; SEOM reports payload violations. |
| `sensor_blackout` | STUM high-uncertainty escalation. | STUM gate `HIGH`; GRPO/SEOM hold; route strategy becomes `alternate_route`. |
| `elevator_queue` | Elevator contention and queue uncertainty. | HTD-IRL waits/replans; fleet coordination records elevator conflict. |
| `corridor_conflict` | Multi-robot corridor arbitration. | CRL-MRS yields corridor and defers reservation. |
| `privacy_zone` | Compliance rule for camera-restricted spaces. | SEOM disables camera and reports `C05_privacy_zone`. |

## Runner Notes

A scenario runner should load these YAML files, run `PIC2Pipeline(run_id=scenario_id).step(observation)`, and compare `expected` against the returned `PipelineResult`.

Run it locally with:

```bash
.venv/bin/python -m origami.cli.main scenario
```

The default report is written to `artifacts/reports/scenario_report.json`.

Useful metrics to aggregate:

- final action correctness
- STUM gate distribution
- replan reason count
- SEOM violation count
- GRPO selected reason and risk flags
- CRL-MRS adjustment/conflict count
- audit validity
- per-module p50/p95 latency
