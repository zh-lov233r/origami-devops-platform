"""中文：AMDC 可视化脚本测试，验证图像文件生成且校准后 RMSE 降低。

English: AMDC visualization script test verifying image generation and lower post-calibration RMSE.
"""

from origami.visualization.amdc_drift_plot import generate_amdc_drift_plot


def test_generate_amdc_drift_plot(tmp_path) -> None:
    output_path = tmp_path / "amdc_demo.png"

    metrics = generate_amdc_drift_plot(output_path=output_path, steps=200, seed=3)

    assert output_path.exists()
    assert output_path.stat().st_size > 0
    assert metrics["rmse_after"] < metrics["rmse_before"]

