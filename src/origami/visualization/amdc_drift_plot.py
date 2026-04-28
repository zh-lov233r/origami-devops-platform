"""
中文：AMDC 校准可视化脚本，生成包含三种 drift 和校准前后对比的诊断图。
English: AMDC calibration visualization script generating diagnostics for three drifts and before/after calibration.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
import numpy as np

from origami.models.amdc.calibrator import AMDCCalibrator

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


DEFAULT_OUTPUT = Path("artifacts/reports/amdc_calibration_demo.png")


def generate_amdc_drift_plot(
    output_path: str | Path = DEFAULT_OUTPUT,
    steps: int = 1_000,
    seed: int = 7,
) -> dict[str, float | str | int]:
    """Generate a deterministic AMDC before/after calibration figure."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    series = simulate_amdc_series(steps=steps, seed=seed)
    fig, axes = plt.subplots(2, 2, figsize=(14, 8), dpi=150)

    t = series["t"]
    clean = series["clean"]
    corrupted = series["corrupted"]
    calibrated = series["calibrated"]

    axes[0, 0].plot(t, clean, label="Ground Truth", linewidth=2.0)
    axes[0, 0].plot(t, corrupted, label="Corrupted Input", alpha=0.70)
    axes[0, 0].plot(t, calibrated, label="AMDC Calibrated Output", alpha=0.85)
    axes[0, 0].set_title("A. AMDC Input/Output Before vs After")
    axes[0, 0].set_xlabel("Step")
    axes[0, 0].set_ylabel("Sensor Value")
    axes[0, 0].legend(loc="upper right")
    axes[0, 0].grid(alpha=0.25)

    axes[0, 1].plot(t, series["gaussian_noise"], label="Gaussian Noise", alpha=0.8)
    axes[0, 1].plot(t, series["thermal_drift"], label="Thermal Drift", alpha=0.9)
    axes[0, 1].plot(t, series["bias_drift"], label="Bias Random Walk", alpha=0.9)
    axes[0, 1].set_title("B. Three Drift Components")
    axes[0, 1].set_xlabel("Step")
    axes[0, 1].set_ylabel("Drift Value")
    axes[0, 1].legend(loc="upper right")
    axes[0, 1].grid(alpha=0.25)

    error_before = np.abs(corrupted - clean)
    error_after = np.abs(calibrated - clean)
    axes[1, 0].plot(t, error_before, label="|Corrupted - Ground Truth|", alpha=0.75)
    axes[1, 0].plot(t, error_after, label="|Calibrated - Ground Truth|", alpha=0.85)
    axes[1, 0].plot(t, series["amdc_residual"], label="AMDC Residual", alpha=0.65)
    axes[1, 0].set_title("C. Error Before vs After")
    axes[1, 0].set_xlabel("Step")
    axes[1, 0].set_ylabel("Absolute Error")
    axes[1, 0].legend(loc="upper right")
    axes[1, 0].grid(alpha=0.25)

    rmse_before = rmse(corrupted, clean)
    rmse_after = rmse(calibrated, clean)
    improvement_pct = (1.0 - rmse_after / rmse_before) * 100.0
    bars = axes[1, 1].bar(
        ["Before AMDC", "After AMDC"],
        [rmse_before, rmse_after],
        color=["#E8364E", "#00A88F"],
    )
    axes[1, 1].bar_label(bars, fmt="%.4f")
    axes[1, 1].set_title(f"D. RMSE Improvement: {improvement_pct:.1f}%")
    axes[1, 1].set_ylabel("RMSE")
    axes[1, 1].grid(axis="y", alpha=0.25)

    fig.suptitle("AMDC Calibration Demo: Gaussian Noise + Thermal Drift + Bias Drift", fontsize=14)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(output_path)
    plt.close(fig)

    return {
        "output_path": str(output_path),
        "steps": steps,
        "seed": seed,
        "rmse_before": round(rmse_before, 6),
        "rmse_after": round(rmse_after, 6),
        "improvement_pct": round(improvement_pct, 2),
    }


def simulate_amdc_series(steps: int, seed: int) -> dict[str, np.ndarray]:
    """Simulate clean signal, three drift types, corrupted input, and AMDC output."""
    rng = np.random.default_rng(seed)
    t = np.arange(steps)

    clean = np.sin(t / 80.0) + 0.15 * np.cos(t / 170.0)
    gaussian_noise = rng.normal(0.0, 0.03, size=steps)

    temperature_c = 25.0 + 5.0 * np.sin(t / 300.0)
    thermal_drift = 0.08 * (temperature_c - 25.0) / 100.0

    bias_drift = np.cumsum(rng.normal(0.0, 0.002, size=steps))
    corrupted = clean + gaussian_noise + thermal_drift + bias_drift

    calibrator = AMDCCalibrator(alpha=0.90)
    calibrated = np.zeros(steps)
    amdc_residual = np.zeros(steps)

    for step in range(steps):
        result = calibrator.calibrate(
            {
                "sensor_readings": {"carry_go_position": float(corrupted[step])},
                "sensor_biases": {"carry_go_position": float(bias_drift[step])},
                "temperature_c": float(temperature_c[step]),
            }
        )
        calibrated[step] = result["calibrated_sensors"]["carry_go_position"]
        amdc_residual[step] = result["amdc_residuals"]["carry_go_position"]

    return {
        "t": t,
        "clean": clean,
        "gaussian_noise": gaussian_noise,
        "thermal_drift": thermal_drift,
        "bias_drift": bias_drift,
        "corrupted": corrupted,
        "calibrated": calibrated,
        "amdc_residual": amdc_residual,
    }


def rmse(values: np.ndarray, reference: np.ndarray) -> float:
    return float(np.sqrt(np.mean((values - reference) ** 2)))


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate AMDC drift calibration demo plot.")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output PNG path.")
    parser.add_argument("--steps", type=int, default=1_000, help="Number of simulated time steps.")
    parser.add_argument("--seed", type=int, default=7, help="Random seed.")
    args = parser.parse_args()

    metrics = generate_amdc_drift_plot(
        output_path=args.output,
        steps=args.steps,
        seed=args.seed,
    )
    print(json.dumps(metrics, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

