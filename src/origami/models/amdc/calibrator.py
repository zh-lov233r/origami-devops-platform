"""
中文：AMDC 基础校准器，修正通用传感器偏置和 Carry & Go 五类关键漂移。
English: Basic AMDC calibrator for generic sensor bias and five Carry & Go critical drift types.

Carry & Go drift types covered: floor friction, elevator timing, camera/depth quality,
IMU vibration, and payload scale bias.
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
        reference_friction_mu: float = 0.55,
        reference_elevator_door_delay_s: float = 2.3,
        reference_lux: float = 500.0,
        payload_max_kg: float = 10.0,
    ) -> None:
        """Initialize AMDC calibration parameters and per-sensor bias memory."""
        self.alpha = alpha
        self.thermal_coeff = thermal_coeff
        self.reference_temperature_c = reference_temperature_c
        self.reference_friction_mu = reference_friction_mu
        self.reference_elevator_door_delay_s = reference_elevator_door_delay_s
        self.reference_lux = reference_lux
        self.payload_max_kg = payload_max_kg
        self.bias_estimates: dict[str, float] = {}

    def calibrate(self, observation: dict[str, Any]) -> dict[str, Any]:
        """Calibrate one observation and attach AMDC residual/status metadata."""
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

        carry_go_corrections, carry_go_residuals = self._calibrate_carry_go_context(
            calibrated,
            thermal_offset=thermal_offset,
        )
        if carry_go_corrections:
            calibrated["carry_go_calibration"] = carry_go_corrections
            self._merge_residuals(calibrated, carry_go_residuals)

        calibrated["amdc_status"] = {
            "bias_estimates": dict(self.bias_estimates),
            "thermal_offset": thermal_offset,
            "temperature_c": temperature_c,
            "carry_go_drift_types": list(carry_go_corrections.keys()),
        }
        return calibrated

    def _calibrate_carry_go_context(
        self,
        observation: dict[str, Any],
        thermal_offset: float,
    ) -> tuple[dict[str, Any], dict[str, float]]:
        """Apply Carry & Go-specific corrections for the five required drift types."""
        corrections: dict[str, Any] = {}
        residuals: dict[str, float] = {}

        floor = self._calibrate_floor_friction(observation)
        if floor:
            corrections["floor_friction"] = floor
            residuals["floor_friction"] = floor["residual"]
            observation["floor_friction_mu"] = floor["corrected_mu"]
            observation["speed_scale"] = min(
                float(observation.get("speed_scale", 1.0)),
                floor["recommended_speed_scale"],
            )

        elevator = self._calibrate_elevator_timing(observation)
        if elevator:
            corrections["elevator_timing"] = elevator
            residuals["elevator_timing"] = elevator["residual"]
            observation["elevator_door_delay_s"] = elevator["corrected_delay_s"]

        camera = self._calibrate_camera_depth(observation, thermal_offset=thermal_offset)
        if camera:
            corrections["camera_depth"] = camera
            residuals["camera_depth"] = camera["residual"]
            if "corrected_depth_m" in camera:
                observation["depth_reading_m"] = camera["corrected_depth_m"]
            observation["perception_uncertainty"] = max(
                float(observation.get("perception_uncertainty", 0.0)),
                camera["quality_sigma"],
            )

        imu = self._calibrate_imu_vibration(observation)
        if imu:
            corrections["imu_vibration"] = imu
            residuals["imu_vibration"] = imu["residual"]
            if "corrected_odometry_delta_m" in imu:
                observation["odometry_delta_m"] = imu["corrected_odometry_delta_m"]
            observation["localization_uncertainty"] = max(
                float(observation.get("localization_uncertainty", 0.0)),
                imu["localization_sigma"],
            )

        payload = self._calibrate_payload_scale(observation, thermal_offset=thermal_offset)
        if payload:
            corrections["payload_scale"] = payload
            residuals["payload_scale"] = payload["residual"]
            observation["payload_kg"] = payload["corrected_payload_kg"]
            observation["payload_over_limit"] = payload["over_limit"]

        return corrections, residuals

    def _calibrate_floor_friction(self, observation: dict[str, Any]) -> dict[str, Any]:
        """Estimate surface friction from commanded vs actual velocity."""
        observed_mu = observation.get("floor_mu_observed")
        if observed_mu is None:
            commanded = observation.get("commanded_velocity_mps")
            actual = observation.get("actual_velocity_mps")
            if commanded is None or actual is None or float(commanded) <= 0.0:
                return {}
            velocity_ratio = max(0.0, min(1.2, float(actual) / float(commanded)))
            observed_mu = self.reference_friction_mu * velocity_ratio

        corrected_mu = max(0.05, min(1.0, float(observed_mu)))
        friction_bias = self.reference_friction_mu - corrected_mu
        estimated_bias = self._update_bias("floor_friction_mu", friction_bias)
        residual = abs(estimated_bias)
        recommended_speed_scale = max(0.35, min(1.0, corrected_mu / self.reference_friction_mu))

        return {
            "type": "floor_friction_bias",
            "reference_mu": self.reference_friction_mu,
            "corrected_mu": corrected_mu,
            "bias": estimated_bias,
            "residual": residual,
            "recommended_speed_scale": recommended_speed_scale,
        }

    def _calibrate_elevator_timing(self, observation: dict[str, Any]) -> dict[str, Any]:
        """Estimate elevator door timing correction from observed delay."""
        observed_delay = observation.get("elevator_observed_door_delay_s")
        if observed_delay is None:
            return {}

        expected_delay = float(
            observation.get(
                "elevator_expected_door_delay_s",
                self.reference_elevator_door_delay_s,
            )
        )
        timing_bias = float(observed_delay) - expected_delay
        estimated_bias = self._update_bias("elevator_door_delay_s", timing_bias)
        corrected_delay = expected_delay + estimated_bias

        return {
            "type": "elevator_timing_bias",
            "expected_delay_s": expected_delay,
            "observed_delay_s": float(observed_delay),
            "corrected_delay_s": corrected_delay,
            "bias_s": estimated_bias,
            "residual": abs(estimated_bias),
        }

    def _calibrate_camera_depth(
        self,
        observation: dict[str, Any],
        thermal_offset: float,
    ) -> dict[str, Any]:
        """Correct camera exposure/depth drift and expose perception quality sigma."""
        has_camera_signal = any(
            key in observation
            for key in (
                "camera_lux_current",
                "camera_flicker_hz",
                "depth_reading_m",
                "depth_reference_m",
                "camera_sharpness",
            )
        )
        if not has_camera_signal:
            return {}

        lux_current = float(observation.get("camera_lux_current", self.reference_lux))
        lux_reference = float(observation.get("camera_lux_reference", self.reference_lux))
        lux_delta_ratio = (lux_current - lux_reference) / max(lux_reference, 1.0)
        flicker_hz = float(observation.get("camera_flicker_hz", 0.0))
        flicker_penalty = 0.04 if 95.0 <= flicker_hz <= 105.0 else 0.0
        sharpness = float(observation.get("camera_sharpness", 1.0))
        optical_penalty = max(0.0, 1.0 - sharpness) * 0.08

        depth_bias = 0.0
        corrected_depth = None
        if "depth_reading_m" in observation and "depth_reference_m" in observation:
            raw_depth_bias = float(observation["depth_reading_m"]) - float(
                observation["depth_reference_m"]
            )
            depth_bias = self._update_bias("camera_depth_m", raw_depth_bias)
            corrected_depth = float(observation["depth_reading_m"]) - depth_bias

        exposure_bias = self._update_bias("camera_exposure", lux_delta_ratio * 0.05)
        residual = abs(exposure_bias) + abs(depth_bias) + abs(thermal_offset) + flicker_penalty
        quality_sigma = min(1.0, residual + optical_penalty)
        result: dict[str, Any] = {
            "type": "camera_exposure_or_depth_bias",
            "lux_delta_ratio": lux_delta_ratio,
            "exposure_bias": exposure_bias,
            "depth_bias_m": depth_bias,
            "flicker_hz": flicker_hz,
            "quality_sigma": quality_sigma,
            "residual": residual,
        }
        if corrected_depth is not None:
            result["corrected_depth_m"] = corrected_depth
        return result

    def _calibrate_imu_vibration(self, observation: dict[str, Any]) -> dict[str, Any]:
        """Estimate IMU vibration and odometry bias for mobile base localisation."""
        has_imu_signal = any(
            key in observation
            for key in (
                "imu_vibration_rms",
                "imu_yaw_rate_bias_dps",
                "wheel_odometry_delta_m",
                "visual_odometry_delta_m",
            )
        )
        if not has_imu_signal:
            return {}

        vibration_rms = float(observation.get("imu_vibration_rms", 0.0))
        yaw_bias = self._update_bias(
            "imu_yaw_rate_dps",
            float(observation.get("imu_yaw_rate_bias_dps", 0.0)),
        )
        odometry_bias = 0.0
        corrected_odometry = None
        if "wheel_odometry_delta_m" in observation and "visual_odometry_delta_m" in observation:
            odometry_bias = self._update_bias(
                "wheel_odometry_delta_m",
                float(observation["wheel_odometry_delta_m"])
                - float(observation["visual_odometry_delta_m"]),
            )
            corrected_odometry = float(observation["wheel_odometry_delta_m"]) - odometry_bias

        vibration_sigma = min(1.0, vibration_rms * 0.20)
        residual = abs(yaw_bias) / 10.0 + abs(odometry_bias) + vibration_sigma
        result: dict[str, Any] = {
            "type": "imu_vibration_bias",
            "vibration_rms": vibration_rms,
            "yaw_bias_dps": yaw_bias,
            "odometry_bias_m": odometry_bias,
            "localization_sigma": min(1.0, residual),
            "residual": residual,
        }
        if corrected_odometry is not None:
            result["corrected_odometry_delta_m"] = corrected_odometry
        return result

    def _calibrate_payload_scale(
        self,
        observation: dict[str, Any],
        thermal_offset: float,
    ) -> dict[str, Any]:
        """Correct payload scale zero drift and thermal scale drift."""
        scale_reading = observation.get("payload_scale_reading_kg")
        if scale_reading is None:
            return {}

        explicit_bias = observation.get("payload_scale_bias_kg")
        if explicit_bias is not None:
            raw_bias = float(explicit_bias)
        elif "payload_reference_kg" in observation:
            raw_bias = float(scale_reading) - float(observation["payload_reference_kg"])
        else:
            raw_bias = 0.0

        thermal_payload_bias = thermal_offset * 10.0
        estimated_bias = self._update_bias("payload_scale_kg", raw_bias + thermal_payload_bias)
        corrected_payload = max(0.0, float(scale_reading) - estimated_bias)

        return {
            "type": "payload_scale_bias",
            "raw_payload_kg": float(scale_reading),
            "corrected_payload_kg": corrected_payload,
            "bias_kg": estimated_bias,
            "residual": abs(estimated_bias),
            "over_limit": corrected_payload > self.payload_max_kg,
        }

    def _calibrate_sensor_map(
        self,
        sensor_readings: Mapping[str, Any],
        sensor_biases: Any,
        thermal_offset: float,
    ) -> tuple[dict[str, Any], dict[str, float]]:
        """Apply bias and thermal correction to each named sensor reading."""
        corrected: dict[str, Any] = {}
        residuals: dict[str, float] = {}

        for sensor_name, reading in sensor_readings.items():
            raw_bias = self._sensor_bias(sensor_biases, sensor_name)
            estimated_bias = self._update_bias(sensor_name, raw_bias)
            total_correction = estimated_bias + thermal_offset
            corrected[sensor_name] = self._subtract(reading, total_correction)
            residuals[sensor_name] = abs(total_correction)

        return corrected, residuals

    def _merge_residuals(
        self,
        observation: dict[str, Any],
        carry_go_residuals: dict[str, float],
    ) -> None:
        """Merge Carry & Go residuals into the standard AMDC residual fields."""
        residuals = dict(observation.get("amdc_residuals", {}))
        residuals.update(carry_go_residuals)
        observation["amdc_residuals"] = residuals
        observation["amdc_residual"] = self._mean_abs(residuals.values())

    def _update_bias(self, sensor_name: str, observed_bias: float) -> float:
        """Update and return the EMA bias estimate for one sensor."""
        previous = self.bias_estimates.get(sensor_name, 0.0)
        estimate = self.alpha * previous + (1.0 - self.alpha) * observed_bias
        self.bias_estimates[sensor_name] = estimate
        return estimate

    @staticmethod
    def _sensor_bias(sensor_biases: Any, sensor_name: str) -> float:
        """Read the configured bias for one sensor from a mapping or scalar value."""
        if isinstance(sensor_biases, Mapping):
            return float(sensor_biases.get(sensor_name, 0.0))
        return float(sensor_biases or 0.0)

    @staticmethod
    def _subtract(value: Any, correction: float) -> Any:
        """Subtract a scalar correction from numeric scalar or sequence readings."""
        if isinstance(value, Sequence) and not isinstance(value, str):
            return [float(item) - correction for item in value]
        if isinstance(value, int | float):
            return float(value) - correction
        return value

    @staticmethod
    def _mean_abs(values: Any) -> float:
        """Compute the mean absolute value for residual aggregation."""
        values = list(values)
        if not values:
            return 0.0
        return sum(abs(float(value)) for value in values) / len(values)
