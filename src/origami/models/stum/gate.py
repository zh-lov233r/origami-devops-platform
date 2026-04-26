"""中文：STUM 三层告警门控，根据总不确定性输出 LOW、MEDIUM 或 HIGH。

English: STUM three-tier alert gate that maps total uncertainty to LOW, MEDIUM, or HIGH.
"""

from __future__ import annotations

from typing import Any


class STUMGate:
    """Three-tier uncertainty gate."""

    def __init__(self, low_threshold: float = 0.10, high_threshold: float = 0.20) -> None:
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold

    def evaluate(self, observation: dict[str, Any]) -> dict[str, Any]:
        output = dict(observation)
        sigma_total = float(output.get("amdc_residual", 0.0)) + 0.03
        if sigma_total < self.low_threshold:
            gate = "LOW"
        elif sigma_total < self.high_threshold:
            gate = "MEDIUM"
        else:
            gate = "HIGH"
        output["sigma_total"] = sigma_total
        output["stum_gate"] = gate
        return output
