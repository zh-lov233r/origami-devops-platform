"""
中文：PIC 2.0 六个基础模块的单元测试，验证校准、门控、规划、决策、安全和协同逻辑。
English: Unit tests for the six basic PIC 2.0 modules covering calibration, gating, planning, policy, safety, and coordination.
"""

from origami.models.amdc.calibrator import AMDCCalibrator
from origami.models.crl_mrs.coordinator import CRLMRSCoordinator
from origami.models.grpo.policy import GRPOPolicy
from origami.models.htd_irl.planner import HTDIRLPlanner
from origami.models.seom.checker import SEOMChecker
from origami.models.stum.gate import STUMGate


def test_amdc_calibrates_sensor_map_and_tracks_residual() -> None:
    calibrator = AMDCCalibrator(alpha=0.0)

    result = calibrator.calibrate(
        {
            "sensor_readings": {"imu": [1.0, 2.0], "scale": 10.0},
            "sensor_biases": {"imu": 0.1, "scale": 0.3},
            "temperature_c": 25.0,
        }
    )

    assert result["calibrated_sensors"]["imu"] == [0.9, 1.9]
    assert result["calibrated_sensors"]["scale"] == 9.7
    assert result["amdc_residual"] > 0.0


def test_amdc_calibrates_carry_go_required_drifts() -> None:
    calibrator = AMDCCalibrator(alpha=0.0)

    result = calibrator.calibrate(
        {
            "floor_mu_observed": 0.35,
            "elevator_expected_door_delay_s": 2.3,
            "elevator_observed_door_delay_s": 4.2,
            "camera_lux_reference": 500.0,
            "camera_lux_current": 150.0,
            "camera_flicker_hz": 100.0,
            "camera_sharpness": 0.75,
            "depth_reading_m": 2.4,
            "depth_reference_m": 2.0,
            "imu_vibration_rms": 0.6,
            "imu_yaw_rate_bias_dps": 1.2,
            "wheel_odometry_delta_m": 1.3,
            "visual_odometry_delta_m": 1.0,
            "payload_scale_reading_kg": 10.3,
            "payload_reference_kg": 10.0,
            "temperature_c": 25.0,
        }
    )

    carry_go = result["carry_go_calibration"]

    assert set(carry_go) == {
        "floor_friction",
        "elevator_timing",
        "camera_depth",
        "imu_vibration",
        "payload_scale",
    }
    assert result["floor_friction_mu"] == 0.35
    assert result["speed_scale"] < 1.0
    assert result["elevator_door_delay_s"] == 4.2
    assert result["depth_reading_m"] == 2.0
    assert result["odometry_delta_m"] == 1.0
    assert result["payload_kg"] == 10.0
    assert result["payload_over_limit"] is False
    assert result["perception_uncertainty"] > 0.0
    assert result["localization_uncertainty"] > 0.0
    assert result["amdc_status"]["carry_go_drift_types"] == [
        "floor_friction",
        "elevator_timing",
        "camera_depth",
        "imu_vibration",
        "payload_scale",
    ]


def test_stum_escalates_when_sensor_blackout_occurs() -> None:
    gate = STUMGate()

    result = gate.evaluate({"sensor_blackout": True, "state_age_s": 1.0})

    assert result["stum_gate"] == "HIGH"
    assert result["autonomy_mode"] == "HALT_OR_ESCALATE"


def test_stum_uses_carry_go_amdc_residuals_and_freshness() -> None:
    gate = STUMGate()

    result = gate.evaluate(
        {
            "mission_type": "carry_go_delivery",
            "current_zone": "elevator",
            "amdc_residuals": {
                "camera_depth": 0.12,
                "imu_vibration": 0.09,
                "payload_scale": 0.02,
            },
            "perception_uncertainty": 0.03,
            "localization_uncertainty": 0.04,
            "sensor_age_s": {"camera": 3.0, "imu": 0.1},
            "sensor_max_age_s": {"camera": 1.0, "imu": 1.0},
            "state_age_s": 2.0,
        }
    )

    assert result["sigma_spatial"] > 0.0
    assert result["sigma_temporal"] > 0.0
    assert result["stum_breakdown"]["spatial"]["carry_go_residual"] > 0.0
    assert result["stum_breakdown"]["temporal"]["stale_sensor_count"] == 1.0
    assert result["autonomy_mode"] in {"CAUTION", "HALT_OR_ESCALATE"}


def test_stum_reports_model_disagreement_ece_and_prediction_interval() -> None:
    gate = STUMGate()

    result = gate.evaluate(
        {
            "ensemble_predictions": [0.2, 0.4, 0.8],
            "route_ambiguity": 0.05,
            "calibration_samples": [
                {"confidence": 0.9, "correct": True},
                {"confidence": 0.8, "correct": False},
                {"confidence": 0.2, "correct": False},
            ],
            "prediction_value": 4.0,
            "conformal_radius": 0.5,
        }
    )

    assert result["sigma_model"] > 0.0
    assert result["ece"] >= 0.0
    assert result["prediction_interval"] == {
        "lower": 3.5,
        "value": 4.0,
        "upper": 4.5,
        "radius": 0.5,
    }
    assert result["stum_recommendation"] in {
        "PROCEED_WITH_CAUTION",
        "HALT_OR_ESCALATE",
        "REPLAN_BEFORE_ACTION",
        "ESTOP_AND_REQUEST_OPERATOR",
    }


def test_htd_irl_builds_carry_go_task_graph_and_replans() -> None:
    planner = HTDIRLPlanner()

    result = planner.plan(
        {
            "mission_type": "carry_go_delivery",
            "elevator_required": True,
            "should_replan": True,
            "blocked_paths": ["main_corridor"],
        }
    )

    assert result["task_graph"]["level_1"] == "deliver_payload"
    assert "request_elevator" in result["task_plan"]
    assert result["replan_level"] == 3
    assert result["route_strategy"] == "alternate_route"
    assert "blocked_path" in result["replan_reasons"]
    assert result["task_status"]["localize"] == "active"
    assert result["htd_irl"]["candidate_count"] > 0


def test_htd_irl_tracks_task_progress_and_candidates() -> None:
    planner = HTDIRLPlanner()

    result = planner.plan(
        {
            "mission_type": "carry_go_delivery",
            "completed_subtasks": ["localize", "navigate_to_pickup"],
            "payload_locked": True,
        }
    )

    assert result["current_subtask"] == "verify_payload"
    assert result["task_status"]["localize"] == "completed"
    assert result["task_status"]["verify_payload"] == "active"
    assert result["task_progress"] > 0.0
    assert {"move": "hold", "speed_mps": 0.0} in result["candidate_actions"]
    assert result["htd_irl"]["active_subtask"] == "verify_payload"


def test_htd_irl_safe_replan_for_battery_or_payload_risk() -> None:
    planner = HTDIRLPlanner()

    low_battery = planner.plan(
        {
            "mission_type": "carry_go_delivery",
            "battery_pct": 10.0,
        }
    )
    payload_risk = planner.plan(
        {
            "mission_type": "carry_go_delivery",
            "payload_over_limit": True,
        }
    )

    assert low_battery["replan_level"] == 1
    assert low_battery["route_strategy"] == "safe_halt_or_return"
    assert low_battery["candidate_actions"][0]["move"] == "return_to_dock"
    assert "return_to_dock" in low_battery["recovery_actions"]
    assert payload_risk["replan_level"] == 1
    assert payload_risk["candidate_actions"] == [{"move": "hold", "speed_mps": 0.0}]


def test_grpo_prefers_action_that_reduces_distance() -> None:
    policy = GRPOPolicy()

    action = policy.decide({"position": [0, 0], "target": [1, 0], "sigma_total": 0.02})

    assert action["move"] == "east"
    assert action["grpo"]["selected_advantage"] > 0
    assert action["grpo"]["selected_breakdown"]["progress"] > 0
    assert abs(sum(action["grpo"]["action_distribution"].values()) - 1.0) < 0.000001


def test_grpo_returns_to_dock_on_low_battery() -> None:
    policy = GRPOPolicy()

    action = policy.decide(
        {
            "position": [0, 0],
            "target": [3, 0],
            "battery_pct": 10.0,
            "sigma_total": 0.01,
        }
    )

    assert action["move"] == "return_to_dock"
    assert action["speed_mps"] <= 0.3
    assert action["grpo"]["selected_reason"] == "low_battery_return"
    assert "low_battery" in action["grpo"]["risk_flags"]


def test_grpo_holds_for_near_human_or_payload_risk() -> None:
    policy = GRPOPolicy()

    near_human_action = policy.decide(
        {
            "position": [0, 0],
            "target": [1, 0],
            "nearest_human_distance_m": 0.2,
            "sigma_total": 0.01,
        }
    )
    payload_action = policy.decide(
        {
            "position": [0, 0],
            "target": [1, 0],
            "payload_over_limit": True,
            "sigma_total": 0.01,
        }
    )

    assert near_human_action["move"] == "hold"
    assert near_human_action["grpo"]["selected_reason"] == "human_safety_hold"
    assert "human_nearby" in near_human_action["grpo"]["risk_flags"]
    assert payload_action["move"] == "hold"
    assert payload_action["grpo"]["selected_reason"] == "payload_safety_hold"


def test_grpo_adds_task_aligned_elevator_and_handoff_actions() -> None:
    policy = GRPOPolicy()

    elevator_action = policy.decide(
        {
            "current_subtask": "request_elevator",
            "position": [0, 0],
            "target": [0, 0],
            "sigma_total": 0.01,
        }
    )
    handoff_action = policy.decide(
        {
            "current_subtask": "handoff_payload",
            "recipient_authenticated": True,
            "position": [0, 0],
            "target": [0, 0],
            "sigma_total": 0.01,
        }
    )

    assert elevator_action["move"] == "enter_elevator"
    assert elevator_action["grpo"]["selected_reason"] == "task_aligned_elevator"
    assert "enter_elevator@0.20" in elevator_action["grpo"]["action_distribution"]
    assert handoff_action["move"] == "handoff_payload"
    assert handoff_action["grpo"]["selected_reason"] == "task_aligned_handoff"


def test_seom_holds_when_human_is_too_close() -> None:
    checker = SEOMChecker()

    checked = checker.check(
        {
            "move": "east",
            "speed_mps": 0.4,
            "state": {"nearest_human_distance_m": 0.2, "stum_gate": "LOW"},
        }
    )

    assert checked["move"] == "hold"
    assert checked["seom_passed"] is False
    assert "C01_person_stop_300mm" in checked["violations"]
    assert checked["gradient_mask"] == "zero"
    assert checked["requires_human_review"] is True


def test_seom_reports_life_safety_penalty_and_audit() -> None:
    checker = SEOMChecker()

    checked = checker.check(
        {
            "move": "east",
            "speed_mps": 0.4,
            "state": {
                "should_estop": True,
                "stum_gate": "HIGH",
                "nearest_human_distance_m": 2.0,
            },
        }
    )

    assert checked["move"] == "hold"
    assert checked["speed_mps"] == 0.0
    assert checked["emergency_stop"] is True
    assert checked["safety_score"] == 0.0
    assert checked["seom_penalty"] == checker.lambda_weight
    assert checked["gradient_mask"] == "zero"
    assert "C12_emergency_stop" in checked["life_safety_violations"]
    assert checked["seom_audit"]["output_action"]["move"] == "hold"
    assert checked["rule_details"]["C12_emergency_stop"]["life_safety"] is True


def test_seom_handles_elevator_and_handoff_safety() -> None:
    checker = SEOMChecker()

    elevator_checked = checker.check(
        {
            "move": "enter_elevator",
            "speed_mps": 0.3,
            "state": {
                "stum_gate": "LOW",
                "nearest_human_distance_m": 2.0,
                "elevator_capacity_remaining": 0,
                "fleet_context": {"same_elevator_conflict": True},
            },
        }
    )
    handoff_checked = checker.check(
        {
            "move": "handoff_payload",
            "speed_mps": 0.0,
            "state": {
                "stum_gate": "LOW",
                "nearest_human_distance_m": 2.0,
                "recipient_authenticated": False,
            },
        }
    )

    assert elevator_checked["move"] == "hold"
    assert "C09_elevator_capacity" in elevator_checked["violations"]
    assert elevator_checked["gradient_mask"] == "reduced"
    assert handoff_checked["move"] == "hold"
    assert "C10_handoff_auth" in handoff_checked["life_safety_violations"]
    assert handoff_checked["requires_human_review"] is True


def test_seom_returns_to_dock_on_low_battery() -> None:
    checker = SEOMChecker()

    checked = checker.check(
        {
            "move": "east",
            "speed_mps": 0.4,
            "state": {
                "battery_pct": 10.0,
                "stum_gate": "LOW",
                "nearest_human_distance_m": 2.0,
            },
        }
    )

    assert checked["move"] == "return_to_dock"
    assert checked["speed_mps"] <= 0.30
    assert checked["gradient_mask"] == "reduced"
    assert "C07_battery_return_15pct" in checked["operational_violations"]


def test_crl_mrs_yields_to_corridor_conflict() -> None:
    coordinator = CRLMRSCoordinator()

    coordinated = coordinator.coordinate(
        {
            "move": "east",
            "speed_mps": 0.4,
            "grpo": {"selected_advantage": 1.0},
            "state": {"fleet_context": {"corridor_occupied": True}},
        }
    )

    assert coordinated["move"] == "hold"
    assert coordinated["fleet_adjustment"] == "yield_corridor"
    assert "yield_corridor" in coordinated["crl_mrs"]["cooperation_events"]
    assert "corridor_conflict" in coordinated["crl_mrs"]["conflict_events"]


def test_crl_mrs_records_elevator_conflict_and_reservation() -> None:
    coordinator = CRLMRSCoordinator()

    coordinated = coordinator.coordinate(
        {
            "move": "enter_elevator",
            "speed_mps": 0.2,
            "grpo": {"selected_advantage": 0.5},
            "state": {
                "robot_id": "r1",
                "current_subtask": "request_elevator",
                "fleet_context": {
                    "elevator_queue": True,
                    "same_elevator_conflict": True,
                    "same_elevator_conflict_with": "r2",
                },
            },
        }
    )

    assert coordinated["move"] == "hold"
    assert coordinated["fleet_adjustment"] == "avoid_elevator_conflict"
    assert coordinated["reservation_request"]["resource"] == "elevator"
    assert coordinated["reservation_request"]["status"] == "deferred"
    assert "same_elevator_conflict" in coordinated["crl_mrs"]["conflict_events"]
    assert coordinated["crl_mrs"]["conflict_graph"]["conflicts"][0]["resource"] == "elevator"


def test_crl_mrs_can_claim_corridor_with_higher_priority() -> None:
    coordinator = CRLMRSCoordinator()

    coordinated = coordinator.coordinate(
        {
            "move": "east",
            "speed_mps": 0.4,
            "grpo": {"selected_advantage": 1.0},
            "state": {
                "robot_id": "urgent-bot",
                "task_priority": 5.0,
                "deadline_slack_s": 20.0,
                "fleet_context": {
                    "corridor_occupied": True,
                    "corridor_occupied_by": "slow-bot",
                    "corridor_peer_priority": 1.0,
                },
            },
        }
    )

    assert coordinated["move"] == "east"
    assert coordinated["fleet_adjustment"] == "claim_corridor_priority"
    assert coordinated["reservation_request"]["status"] == "requested"
    assert "claim_corridor" in coordinated["crl_mrs"]["resource_events"]
    assert coordinated["crl_mrs"]["priority_score"] > 5.0
