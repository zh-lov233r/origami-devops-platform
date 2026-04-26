"""中文：SEOM 安全检查器占位实现，在高不确定性场景下将动作覆盖为 hold。

English: Placeholder SEOM safety checker that overrides actions to hold under high uncertainty.
"""

from __future__ import annotations

from typing import Any


class SEOMChecker:
    """Placeholder constitutional safety checker."""

    def check(self, action: dict[str, Any]) -> dict[str, Any]:
        checked = dict(action)
        unsafe_gate = action.get("state", {}).get("stum_gate") == "HIGH"
        if unsafe_gate:
            checked["move"] = "hold"
        checked["seom_passed"] = not unsafe_gate
        checked["rules_checked"] = ["R1_uncertainty_halt"]
        return checked
