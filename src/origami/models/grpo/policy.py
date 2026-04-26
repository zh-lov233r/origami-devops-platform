"""中文：GRPO 策略占位实现，根据 STUM 风险门控提出下一步动作。

English: Placeholder GRPO policy implementation that proposes the next action from STUM risk gating.
"""

from __future__ import annotations

from typing import Any


class GRPOPolicy:
    """Placeholder group-relative policy."""

    def decide(self, state: dict[str, Any]) -> dict[str, Any]:
        gate = state.get("stum_gate", "LOW")
        move = "hold" if gate == "HIGH" else "east"
        return {
            "move": move,
            "confidence": 1.0 - float(state.get("sigma_total", 0.0)),
            "state": state,
        }
