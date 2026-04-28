"""中文：STUM 基础不确定性模块，计算空间/时间不确定性并输出三层告警。

English: Basic STUM uncertainty module that computes spatial/temporal uncertainty and emits a three-tier gate.
"""

from __future__ import annotations

from math import exp, sqrt
from typing import Any


class STUMGate:
    """Spatiotemporal uncertainty gate with calibrated-style outputs."""

    def __init__(
        self,
        low_threshold: float = 0.10,
        high_threshold: float = 0.20,
        replan_threshold: float = 0.60,
        temporal_base_sigma: float = 0.02,
        temporal_decay_k: float = 0.08,
    ) -> None:
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.replan_threshold = replan_threshold
        self.temporal_base_sigma = temporal_base_sigma
        self.temporal_decay_k = temporal_decay_k

    def evaluate(self, observation: dict[str, Any]) -> dict[str, Any]:
        output = dict(observation)
        sigma_spatial = self._spatial_uncertainty(output)
        sigma_temporal = self._temporal_uncertainty(output)
        sigma_total = min(1.0, sqrt(sigma_spatial**2 + sigma_temporal**2))

        if sigma_total < self.low_threshold:
            gate = "LOW"
            autonomy_mode = "AUTONOMOUS"
        elif sigma_total < self.high_threshold:
            gate = "MEDIUM"
            autonomy_mode = "CAUTION"
        else:
            gate = "HIGH"
            autonomy_mode = "HALT_OR_ESCALATE"

        output["sigma_spatial"] = sigma_spatial
        output["sigma_temporal"] = sigma_temporal
        output["sigma_total"] = sigma_total
        output["stum_gate"] = gate
        output["autonomy_mode"] = autonomy_mode
        output["confidence"] = max(0.0, 1.0 - sigma_total)
        output["should_replan"] = sigma_total >= self.replan_threshold
        return output

    def _spatial_uncertainty(self, observation: dict[str, Any]) -> float:
        amdc_residual = float(observation.get("amdc_residual", 0.0))
        perception_uncertainty = float(observation.get("perception_uncertainty", 0.0))
        dropout_penalty = 0.35 if observation.get("sensor_blackout") else 0.0
        return min(1.0, amdc_residual + perception_uncertainty + dropout_penalty)

    def _temporal_uncertainty(self, observation: dict[str, Any]) -> float:
        state_age_s = max(0.0, float(observation.get("state_age_s", 0.0)))
        context_k = float(observation.get("temporal_decay_k", self.temporal_decay_k))
        return min(1.0, self.temporal_base_sigma * exp(context_k * state_age_s))
