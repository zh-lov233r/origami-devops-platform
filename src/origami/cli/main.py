"""
中文：命令行主入口，提供 smoke、benchmark、export、edge mock 和 audit verify 命令。
English: Main command-line entrypoint for smoke, benchmark, export, edge mock, and audit verify commands.
"""

from __future__ import annotations

import argparse
import json

from origami.audit.chain import AuditChain
from origami.benchmark.runner import run_latency_benchmark
from origami.core.pipeline import PIC2Pipeline
from origami.edge.mock_runtime import run_edge_mock
from origami.export.onnx_export import export_placeholder


def run_smoke() -> None:
    pipeline = PIC2Pipeline(run_id="smoke")
    observation = {
        "mission_type": "carry_go_delivery",
        "position": [0, 0],
        "target": [1, 1],
        "sensor_bias": 0.02,
        "payload_kg": 2.0,
        "payload_locked": True,
        "battery_pct": 80,
        "nearest_human_distance_m": 2.0,
        "floor_mu_observed": 0.50,
        "elevator_expected_door_delay_s": 2.3,
        "elevator_observed_door_delay_s": 2.5,
        "camera_lux_reference": 500.0,
        "camera_lux_current": 450.0,
        "camera_sharpness": 0.95,
        "depth_reading_m": 2.05,
        "depth_reference_m": 2.0,
        "imu_vibration_rms": 0.10,
        "imu_yaw_rate_bias_dps": 0.20,
        "wheel_odometry_delta_m": 1.02,
        "visual_odometry_delta_m": 1.0,
        "payload_scale_reading_kg": 2.1,
        "payload_reference_kg": 2.0,
        "fleet_context": {"nearby_robots": 0},
    }
    result = pipeline.step(observation)
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))


def run_audit_verify() -> None:
    chain = AuditChain()
    chain.append(
        run_id="manual",
        step=0,
        observation={"position": [0, 0]},
        proposed_action={"move": "east"},
        final_action={"move": "east"},
        metadata={"source": "cli"},
    )
    ok, index = chain.verify()
    print(json.dumps({"valid": ok, "failed_index": index}, indent=2, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(prog="origami")
    parser.add_argument(
        "command",
        choices=["smoke", "benchmark", "export", "edge-mock", "audit-verify"],
        help="Platform command to run.",
    )
    args = parser.parse_args()

    if args.command == "smoke":
        run_smoke()
    elif args.command == "benchmark":
        print(json.dumps(run_latency_benchmark(), indent=2, sort_keys=True))
    elif args.command == "export":
        print(json.dumps(export_placeholder(), indent=2, sort_keys=True))
    elif args.command == "edge-mock":
        print(json.dumps(run_edge_mock(), indent=2, sort_keys=True))
    elif args.command == "audit-verify":
        run_audit_verify()


if __name__ == "__main__":
    main()
