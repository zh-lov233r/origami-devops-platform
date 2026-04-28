"""中文：AMDC 基础校准器，用 EMA、热漂移和传感器偏置修正模拟观测。

English: Basic AMDC calibrator that corrects simulated observations with EMA, thermal drift, and sensor bias.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


class AMDCCalibrator:
    """Lightweight Adaptive Multi-Domain Calibration module.

    The basic version supports two input styles:
    - top-level `sensor_bias` for quick smoke tests
    - `sensor_readings` + optional `sensor_biases` for multi-sensor scenarios
    """

    def __init__(
        self,
        alpha: float = 0.85,
        thermal_coeff: float = 0.08,
        reference_temperature_c: float = 25.0,
    ) -> None:
        self.alpha = alpha
        self.thermal_coeff = thermal_coeff
        self.reference_temperature_c = reference_temperature_c
        self.bias_estimates: dict[str, float] = {}

    def calibrate(self, observation: dict[str, Any]) -> dict[str, Any]:
        calibrated = dict(observation)
        temperature_c = float(calibrated.get("temperature_c", self.reference_temperature_c))
        thermal_offset = self.thermal_coeff * (
            temperature_c - self.reference_temperature_c
        ) / 100.0

        sensor_readings = calibrated.get("sensor_readings")
        if isinstance(sensor_readings, Mapping):
            corrected_readings, residuals = self._calibrate_sensor_map(
                sensor_readings=sensor_readings,
                sensor_biases=calibrated.get("sensor_biases", {}),
                thermal_offset=thermal_offset,
            )
            calibrated["calibrated_sensors"] = corrected_readings
            calibrated["amdc_residuals"] = residuals
            calibrated["amdc_residual"] = self._mean_abs(residuals.values())
        else:
            bias = float(calibrated.get("sensor_bias", 0.0))
            estimated_bias = self._update_bias("default", bias)
            calibrated["amdc_residual"] = abs(estimated_bias) + abs(thermal_offset)
            calibrated["sensor_bias"] = 0.0

        calibrated["amdc_status"] = {
            "bias_estimates": dict(self.bias_estimates),
            "thermal_offset": thermal_offset,
            "temperature_c": temperature_c,
        }
        return calibrated

    def _calibrate_sensor_map(
        self,
        sensor_readings: Mapping[str, Any],
        sensor_biases: Any,
        thermal_offset: float,
    ) -> tuple[dict[str, Any], dict[str, float]]:
        corrected: dict[str, Any] = {}
        residuals: dict[str, float] = {}

        for sensor_name, reading in sensor_readings.items():
            raw_bias = self._sensor_bias(sensor_biases, sensor_name)
            estimated_bias = self._update_bias(sensor_name, raw_bias)
            total_correction = estimated_bias + thermal_offset
            corrected[sensor_name] = self._subtract(reading, total_correction)
            residuals[sensor_name] = abs(total_correction)

        return corrected, residuals

    def _update_bias(self, sensor_name: str, observed_bias: float) -> float:
        previous = self.bias_estimates.get(sensor_name, 0.0)
        estimate = self.alpha * previous + (1.0 - self.alpha) * observed_bias
        self.bias_estimates[sensor_name] = estimate
        return estimate

    @staticmethod
    def _sensor_bias(sensor_biases: Any, sensor_name: str) -> float:
        if isinstance(sensor_biases, Mapping):
            return float(sensor_biases.get(sensor_name, 0.0))
        return float(sensor_biases or 0.0)

    @staticmethod
    def _subtract(value: Any, correction: float) -> Any:
        if isinstance(value, Sequence) and not isinstance(value, str):
            return [float(item) - correction for item in value]
        if isinstance(value, int | float):
            return float(value) - correction
        return value

    @staticmethod
    def _mean_abs(values: Any) -> float:
        values = list(values)
        if not values:
            return 0.0
        return sum(abs(float(value)) for value in values) / len(values)
