"""
中文：Pipeline smoke 测试，验证六阶段 pipeline 可以完成一个最小 step。
English: Pipeline smoke test verifying the six-stage pipeline can complete one minimal step.
"""

from origami.core.pipeline import PIC2Pipeline


def test_pipeline_smoke_step() -> None:
    pipeline = PIC2Pipeline(run_id="test")
    result = pipeline.step(
        {
            "mission_type": "carry_go_delivery",
            "position": [0, 0],
            "target": [1, 1],
            "sensor_bias": 0.02,
            "payload_kg": 2.0,
            "payload_locked": True,
            "battery_pct": 80,
            "nearest_human_distance_m": 2.0,
            "fleet_context": {"nearby_robots": 0},
        }
    )

    assert result.audit_valid is True
    assert result.action["move"] in {"east", "north", "hold", "return_to_dock"}
    assert result.action["seom_passed"] is True
    assert "crl_mrs" in result.action
    assert [event.module for event in result.events] == [
        "amdc",
        "stum",
        "htd_irl",
        "grpo",
        "seom",
        "crl_mrs",
    ]
