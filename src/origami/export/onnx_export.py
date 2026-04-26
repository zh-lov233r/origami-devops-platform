"""中文：ONNX 导出占位入口，描述未来 GRPO 和 STUM 模型导出位置。

English: Placeholder ONNX export entrypoint describing where future GRPO and STUM model exports will live.
"""

from __future__ import annotations


def export_placeholder() -> dict[str, object]:
    return {
        "status": "placeholder",
        "format": "onnx",
        "models": ["grpo_policy", "stum_ensemble"],
        "next_step": "replace placeholder with torch.onnx.export once models exist",
    }
