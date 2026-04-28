"""
中文：pipeline 结构化事件定义，用于记录模块名和延迟等观测数据。
English: Structured pipeline event definitions for recording module names, latency, and related telemetry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PipelineEvent:
    module: str
    latency_ms: float

    def to_dict(self) -> dict[str, float | str]:
        return {
            "module": self.module,
            "latency_ms": round(self.latency_ms, 4),
        }
