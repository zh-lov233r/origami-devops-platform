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


def test_grpo_prefers_action_that_reduces_distance() -> None:
    policy = GRPOPolicy()

    action = policy.decide({"position": [0, 0], "target": [1, 0], "sigma_total": 0.02})

    assert action["move"] == "east"
    assert action["grpo"]["selected_advantage"] > 0


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
