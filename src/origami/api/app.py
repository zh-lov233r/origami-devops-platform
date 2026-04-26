"""
中文：FastAPI 控制面应用，提供健康检查、smoke run 和 latency benchmark 接口。
English: FastAPI control-plane app exposing health, smoke run, and latency benchmark endpoints.
"""

from __future__ import annotations

from fastapi import FastAPI

from origami.benchmark.runner import run_latency_benchmark
from origami.core.pipeline import PIC2Pipeline

app = FastAPI(title="Origami Mini PIC 2.0 DevOps Platform")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/runs/smoke")
def smoke_run() -> dict[str, object]:
    pipeline = PIC2Pipeline(run_id="api-smoke")
    result = pipeline.step({"position": [0, 0], "target": [1, 1], "sensor_bias": 0.0})
    return result.to_dict()


@app.post("/benchmarks/latency")
def latency_benchmark() -> dict[str, object]:
    return run_latency_benchmark()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
