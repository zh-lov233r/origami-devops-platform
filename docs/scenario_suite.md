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

The runner writes these default artifacts:

- `artifacts/reports/scenario_report.json`: machine-readable full report
- `artifacts/reports/scenario_report.md`: human-readable summary table
- `artifacts/events/scenario_events.jsonl`: per-module latency events
- `artifacts/audit/scenario_audit.jsonl`: tamper-evident audit chain entries

## Multi-Step Scenarios

Multi-step scenarios live in `configs/multistep_scenarios/` and run one
`PIC2Pipeline` across a timeline. Each step inherits the previous observation,
optionally advances position from the previous action, applies an
`observation_patch`, and evaluates that step's `expected` assertions.
The runner also supports long-running shorthand:

- Top-level `time_step_s` sets the default simulated interval when a step does
  not provide `at_s`.
- Top-level `battery_drain_pct_per_step`, `battery_drain_pct_per_s`, or
  `battery_drain_pct_per_min` reduces `battery_pct` before each step runs.
- Step-level `repeat` expands one YAML step into multiple pipeline ticks.
- Step-level `interval_s`, `advance_position`, `battery_drain_pct`, and
  `apply_battery_drain` override the defaults for that step.
- Top-level `stop_on_failure: true` stops a scenario after the first failed
  timeline step.
- Multi-step assertions can check timeline fields such as `final_position`,
  `final_battery_pct`, `min_mission_elapsed_s`, and
  `max_distance_to_dock`.

Run them locally with:

```bash
.venv/bin/python -m origami.cli.main multistep-scenario
.venv/bin/python -m origami.cli.main multistep-scenario \
  --multistep-scenario-id delivery_long_return_interruption
```

The default examples include:

| Scenario | Main Purpose |
| --- | --- |
| `delivery_low_battery_return` | Starts a delivery, advances through normal route progress, then drops battery below the return threshold and expects `return_to_dock`, `battery_abort`, and `low_battery` signals. |
| `delivery_long_return_interruption` | Uses repeated cruise ticks and battery drain, then verifies the robot pauses for a human on the return path and resumes docking after the path clears. |

The runner writes:

- `artifacts/reports/multistep_scenario_report.json`
- `artifacts/reports/multistep_scenario_report.md`
- `artifacts/events/multistep_scenario_events.jsonl`
- `artifacts/audit/multistep_scenario_audit.jsonl`

The dashboard Test Lab can run the full multi-step timeline suite or one
selected timeline through the Multi-Step Timeline card.

## Scenario Builder

The dashboard can save custom Carry & Go YAML scenarios into `configs/scenarios/` through `POST /api/scenarios`. The builder writes the same schema as the hand-authored scenarios:

- `observation`: runtime inputs for the six-stage pipeline
- `expected`: assertions evaluated by the scenario runner
- `tags`: dashboard/report grouping labels

Useful metrics to aggregate:

- final action correctness
- STUM gate distribution
- replan reason count
- SEOM violation count
- GRPO selected reason and risk flags
- CRL-MRS adjustment/conflict count
- audit validity
- per-module p50/p95 latency
