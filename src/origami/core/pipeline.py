"""中文：mini PIC 2.0 六阶段 pipeline 运行时，串联 AMDC、STUM、HTD-IRL、GRPO、SEOM 和 CRL-MRS。

English: Mini PIC 2.0 six-stage pipeline runtime connecting AMDC, STUM, HTD-IRL, GRPO, SEOM, and CRL-MRS.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from time import perf_counter
from typing import Any

from origami.audit.chain import AuditChain
from origami.models.amdc.calibrator import AMDCCalibrator
from origami.models.crl_mrs.coordinator import CRLMRSCoordinator
from origami.models.grpo.policy import GRPOPolicy
from origami.models.htd_irl.planner import HTDIRLPlanner
from origami.models.seom.checker import SEOMChecker
from origami.models.stum.gate import STUMGate
from origami.observability.events import PipelineEvent


@dataclass
class PipelineResult:
    run_id: str
    step: int
    observation: dict[str, Any]
    action: dict[str, Any]
    events: list[PipelineEvent] = field(default_factory=list)
    audit_valid: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "step": self.step,
            "observation": self.observation,
            "action": self.action,
            "events": [event.to_dict() for event in self.events],
            "audit_valid": self.audit_valid,
        }


class PIC2Pipeline:
    """Minimal six-stage PIC 2.0 runtime contract."""

    def __init__(self, run_id: str = "local") -> None:
        self.run_id = run_id
        self.step_index = 0
        self.amdc = AMDCCalibrator()
        self.stum = STUMGate()
        self.htd_irl = HTDIRLPlanner()
        self.grpo = GRPOPolicy()
        self.seom = SEOMChecker()
        self.crl_mrs = CRLMRSCoordinator()
        self.audit = AuditChain()

    def step(self, observation: dict[str, Any]) -> PipelineResult:
        events: list[PipelineEvent] = []

        calibrated = self._timed("amdc", events, self.amdc.calibrate, observation)
        uncertainty = self._timed("stum", events, self.stum.evaluate, calibrated)
        plan = self._timed("htd_irl", events, self.htd_irl.plan, uncertainty)
        proposed_action = self._timed("grpo", events, self.grpo.decide, plan)
        checked_action = self._timed("seom", events, self.seom.check, proposed_action)
        final_action = self._timed("crl_mrs", events, self.crl_mrs.coordinate, checked_action)

        self.audit.append(
            run_id=self.run_id,
            step=self.step_index,
            observation=observation,
            proposed_action=proposed_action,
            final_action=final_action,
            metadata={
                "sigma_total": uncertainty.get("sigma_total"),
                "stum_gate": uncertainty.get("stum_gate"),
                "seom_passed": checked_action.get("seom_passed"),
            },
        )
        audit_valid, _ = self.audit.verify()

        result = PipelineResult(
            run_id=self.run_id,
            step=self.step_index,
            observation=calibrated,
            action=final_action,
            events=events,
            audit_valid=audit_valid,
        )
        self.step_index += 1
        return result

    def _timed(self, module: str, events: list[PipelineEvent], fn: Any, payload: dict[str, Any]) -> Any:
        start = perf_counter()
        output = fn(payload)
        latency_ms = (perf_counter() - start) * 1000
        events.append(PipelineEvent(module=module, latency_ms=latency_ms))
        return output
