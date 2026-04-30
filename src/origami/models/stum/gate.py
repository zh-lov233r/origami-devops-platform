"""
中文：STUM 基础不确定性模块，融合 AMDC residual、传感器 freshness 和模型分歧。
English: Basic STUM uncertainty module fusing AMDC residuals, sensor freshness, and model disagreement.
"""

from __future__ import annotations

from math import exp, sqrt
from typing import Any


class STUMGate:
    """Spatiotemporal uncertainty gate with Carry & Go-friendly diagnostics."""

    def __init__(
        self,
        low_threshold: float = 0.10,
        high_threshold: float = 0.20,
        replan_threshold: float = 0.60,
        emergency_threshold: float = 0.80,
        temporal_base_sigma: float = 0.02,
        temporal_decay_k: float = 0.08,
        default_sensor_max_age_s: float = 2.0,
    ) -> None:
        self.low_threshold = low_threshold
        self.high_threshold = high_threshold
        self.replan_threshold = replan_threshold
        self.emergency_threshold = emergency_threshold
        self.temporal_base_sigma = temporal_base_sigma
        self.temporal_decay_k = temporal_decay_k
        self.default_sensor_max_age_s = default_sensor_max_age_s

    def evaluate(self, observation: dict[str, Any]) -> dict[str, Any]:
        output = dict(observation)
        sigma_spatial, spatial_breakdown = self._spatial_uncertainty(output)
        sigma_temporal, temporal_breakdown = self._temporal_uncertainty(output)
        sigma_model, model_breakdown = self._model_uncertainty(output)
        sigma_total = min(1.0, sqrt(sigma_spatial**2 + sigma_temporal**2 + sigma_model**2))

        gate, autonomy_mode = self._gate(sigma_total)
        confidence = max(0.0, 1.0 - sigma_total)
        should_replan = sigma_total >= self.replan_threshold
        ece = self._expected_calibration_error(output.get("calibration_samples", []))

        output["sigma_spatial"] = sigma_spatial
        output["sigma_temporal"] = sigma_temporal
        output["sigma_model"] = sigma_model
        output["sigma_total"] = sigma_total
        output["stum_gate"] = gate
        output["autonomy_mode"] = autonomy_mode
        output["confidence"] = confidence
        output["should_replan"] = should_replan
        output["should_estop"] = sigma_total >= self.emergency_threshold
        output["stum_breakdown"] = {
            "spatial": spatial_breakdown,
            "temporal": temporal_breakdown,
            "model": model_breakdown,
        }
        output["stum_recommendation"] = self._recommendation(
            gate=gate,
            should_replan=should_replan,
            should_estop=output["should_estop"],
        )
        if ece is not None:
            output["ece"] = ece
        interval = self._prediction_interval(output, sigma_total)
        if interval:
            output["prediction_interval"] = interval
        return output

    def _spatial_uncertainty(self, observation: dict[str, Any]) -> tuple[float, dict[str, float]]:
        amdc_residual = float(observation.get("amdc_residual", 0.0))
        perception_uncertainty = float(observation.get("perception_uncertainty", 0.0))
        localization_uncertainty = float(observation.get("localization_uncertainty", 0.0))
        dropout_penalty = 0.35 if observation.get("sensor_blackout") else 0.0
        residuals = observation.get("amdc_residuals", {})
        carry_go_residual = self._weighted_amdc_residual(residuals)
        spatial = min(
            1.0,
            max(amdc_residual, carry_go_residual)
            + perception_uncertainty
            + localization_uncertainty
            + dropout_penalty,
        )
        return spatial, {
            "amdc_residual": amdc_residual,
            "carry_go_residual": carry_go_residual,
            "perception_uncertainty": perception_uncertainty,
            "localization_uncertainty": localization_uncertainty,
            "dropout_penalty": dropout_penalty,
        }

    def _temporal_uncertainty(self, observation: dict[str, Any]) -> tuple[float, dict[str, float]]:
        state_age_s = max(0.0, float(observation.get("state_age_s", 0.0)))
        context_k = self._context_decay_k(observation)
        state_sigma = min(1.0, self.temporal_base_sigma * exp(context_k * state_age_s))
        freshness_sigma, freshness_breakdown = self._sensor_freshness_uncertainty(observation)
        temporal = min(1.0, sqrt(state_sigma**2 + freshness_sigma**2))
        return temporal, {
            "state_age_s": state_age_s,
            "context_decay_k": context_k,
            "state_sigma": state_sigma,
            "freshness_sigma": freshness_sigma,
            **freshness_breakdown,
        }

    def _model_uncertainty(self, observation: dict[str, Any]) -> tuple[float, dict[str, float]]:
        ensemble_predictions = observation.get("ensemble_predictions")
        if isinstance(ensemble_predictions, list) and len(ensemble_predictions) >= 2:
            values = [float(value) for value in ensemble_predictions]
            mean_value = sum(values) / len(values)
            variance = sum((value - mean_value) ** 2 for value in values) / len(values)
            disagreement = min(1.0, sqrt(variance))
        else:
            disagreement = float(observation.get("model_disagreement", 0.0))

        route_ambiguity = float(observation.get("route_ambiguity", 0.0))
        elevator_queue_uncertainty = 0.05 if observation.get("elevator_queue_unknown") else 0.0
        model_sigma = min(1.0, disagreement + route_ambiguity + elevator_queue_uncertainty)
        return model_sigma, {
            "ensemble_disagreement": disagreement,
            "route_ambiguity": route_ambiguity,
            "elevator_queue_uncertainty": elevator_queue_uncertainty,
        }

    def _sensor_freshness_uncertainty(
        self,
        observation: dict[str, Any],
    ) -> tuple[float, dict[str, float]]:
        sensor_ages = observation.get("sensor_age_s", {})
        sensor_max_ages = observation.get("sensor_max_age_s", {})
        if not isinstance(sensor_ages, dict):
            return 0.0, {"stale_sensor_count": 0.0, "max_staleness_ratio": 0.0}

        stale_count = 0
        max_ratio = 0.0
        for sensor_name, age in sensor_ages.items():
            max_age = self.default_sensor_max_age_s
            if isinstance(sensor_max_ages, dict):
                max_age = float(sensor_max_ages.get(sensor_name, self.default_sensor_max_age_s))
            ratio = max(0.0, float(age) / max(max_age, 0.001))
            max_ratio = max(max_ratio, ratio)
            if ratio > 1.0:
                stale_count += 1

        freshness_sigma = min(1.0, max(0.0, max_ratio - 1.0) * 0.12 + stale_count * 0.04)
        return freshness_sigma, {
            "stale_sensor_count": float(stale_count),
            "max_staleness_ratio": max_ratio,
        }

    def _context_decay_k(self, observation: dict[str, Any]) -> float:
        if "temporal_decay_k" in observation:
            return float(observation["temporal_decay_k"])

        mission_type = observation.get("mission_type")
        current_zone = observation.get("current_zone")
        if mission_type == "carry_go_delivery" and current_zone == "elevator":
            return 0.14
        if mission_type == "carry_go_delivery":
            return 0.10
        return self.temporal_decay_k

    def _gate(self, sigma_total: float) -> tuple[str, str]:
        if sigma_total < self.low_threshold:
            return "LOW", "AUTONOMOUS"
        if sigma_total < self.high_threshold:
            return "MEDIUM", "CAUTION"
        return "HIGH", "HALT_OR_ESCALATE"

    @staticmethod
    def _weighted_amdc_residual(residuals: Any) -> float:
        if not isinstance(residuals, dict) or not residuals:
            return 0.0

        weights = {
            "floor_friction": 0.50,
            "elevator_timing": 0.30,
            "camera_depth": 0.80,
            "imu_vibration": 0.90,
            "payload_scale": 0.40,
        }
        weighted_total = 0.0
        total_weight = 0.0
        for name, value in residuals.items():
            weight = weights.get(str(name), 0.50)
            weighted_total += abs(float(value)) * weight
            total_weight += weight
        return min(1.0, weighted_total / max(total_weight, 0.001))

    @staticmethod
    def _expected_calibration_error(samples: Any, bins: int = 10) -> float | None:
        if not isinstance(samples, list) or not samples:
            return None

        buckets = [
            {"count": 0, "confidence": 0.0, "accuracy": 0.0}
            for _ in range(bins)
        ]
        for sample in samples:
            if not isinstance(sample, dict):
                continue
            confidence = max(0.0, min(1.0, float(sample.get("confidence", 0.0))))
            correct = 1.0 if sample.get("correct") else 0.0
            index = min(bins - 1, int(confidence * bins))
            buckets[index]["count"] += 1
            buckets[index]["confidence"] += confidence
            buckets[index]["accuracy"] += correct

        total = sum(bucket["count"] for bucket in buckets)
        if total == 0:
            return None

        ece = 0.0
        for bucket in buckets:
            count = bucket["count"]
            if count == 0:
                continue
            avg_confidence = bucket["confidence"] / count
            avg_accuracy = bucket["accuracy"] / count
            ece += abs(avg_accuracy - avg_confidence) * count / total
        return round(ece, 6)

    @staticmethod
    def _prediction_interval(
        observation: dict[str, Any],
        sigma_total: float,
    ) -> dict[str, float] | None:
        if "prediction_value" not in observation:
            return None

        value = float(observation["prediction_value"])
        conformal_radius = float(observation.get("conformal_radius", 1.96 * sigma_total))
        return {
            "lower": value - conformal_radius,
            "value": value,
            "upper": value + conformal_radius,
            "radius": conformal_radius,
        }

    @staticmethod
    def _recommendation(gate: str, should_replan: bool, should_estop: bool) -> str:
        if should_estop:
            return "ESTOP_AND_REQUEST_OPERATOR"
        if should_replan:
            return "REPLAN_BEFORE_ACTION"
        if gate == "HIGH":
            return "HALT_OR_ESCALATE"
        if gate == "MEDIUM":
            return "PROCEED_WITH_CAUTION"
        return "PROCEED_AUTONOMOUSLY"
