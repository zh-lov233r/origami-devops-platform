"""
中文：Artifact persistence layer，统一写入 JSON、JSONL 和 Markdown 报告文件。
English: Artifact persistence layer for writing JSON, JSONL, and Markdown report files.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class ArtifactStore:
    """Small local-first artifact store rooted under `artifacts/` by default."""

    def __init__(self, root: Path | str = "artifacts") -> None:
        self.root = Path(root)

    def write_json(self, relative_path: Path | str, payload: dict[str, Any]) -> Path:
        """Write a JSON artifact and return its absolute path."""
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return path

    def write_text(self, relative_path: Path | str, content: str) -> Path:
        """Write a text artifact and return its absolute path."""
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def write_jsonl(self, relative_path: Path | str, records: list[dict[str, Any]]) -> Path:
        """Write records as newline-delimited JSON and return the artifact path."""
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(record, sort_keys=True, default=str) for record in records]
        path.write_text("\n".join(lines) + ("\n" if lines else ""))
        return path

    def append_jsonl(self, relative_path: Path | str, records: list[dict[str, Any]]) -> Path:
        """Append records as newline-delimited JSON and return the artifact path."""
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(record, sort_keys=True, default=str) for record in records]
        if lines:
            with path.open("a") as file:
                file.write("\n".join(lines) + "\n")
        return path

    def _resolve(self, relative_path: Path | str) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            return path
        return self.root / path
