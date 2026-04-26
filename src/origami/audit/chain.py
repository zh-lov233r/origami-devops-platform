"""
中文：SHA-256 audit chain 实现，用于记录并验证 pipeline 决策是否被篡改。
English: SHA-256 audit chain implementation for recording and verifying tamper-evident pipeline decisions.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass
class AuditEntry:
    data: dict[str, Any]


class AuditChain:
    """In-memory SHA-256 hash chain for decision traceability."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []
        self.previous_hash = "0" * 64

    def append(
        self,
        run_id: str,
        step: int,
        observation: dict[str, Any],
        proposed_action: dict[str, Any],
        final_action: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> AuditEntry:
        entry = {
            "run_id": run_id,
            "step": step,
            "timestamp": time.time(),
            "observation_hash": self._hash_payload(observation),
            "proposed_action_hash": self._hash_payload(proposed_action),
            "final_action_hash": self._hash_payload(final_action),
            "metadata": metadata or {},
            "previous_hash": self.previous_hash,
        }
        entry["hash"] = self._hash_payload(entry)
        self.previous_hash = entry["hash"]
        audit_entry = AuditEntry(data=entry)
        self.entries.append(audit_entry)
        return audit_entry

    def verify(self) -> tuple[bool, int]:
        previous_hash = "0" * 64
        for index, entry in enumerate(self.entries):
            data = dict(entry.data)
            stored_hash = data.pop("hash")
            if data["previous_hash"] != previous_hash:
                return False, index
            if self._hash_payload(data) != stored_hash:
                return False, index
            previous_hash = stored_hash
        return True, -1

    @staticmethod
    def _hash_payload(payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
