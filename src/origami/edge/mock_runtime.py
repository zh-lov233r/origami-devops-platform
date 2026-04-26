"""中文：边缘部署 mock runtime，模拟 Jetson Orin Nano 的推理预算和运行状态。

English: Edge deployment mock runtime that simulates Jetson Orin Nano inference budgets and runtime readiness.
"""

from __future__ import annotations


def run_edge_mock(profile: str = "jetson_orin_nano_mock") -> dict[str, object]:
    return {
        "profile": profile,
        "runtime": "onnxruntime",
        "latency_budget_ms": 50.0,
        "checks": {
            "model_loaded": "mock",
            "inference_ready": "mock",
            "budget_enforced": True,
        },
    }
