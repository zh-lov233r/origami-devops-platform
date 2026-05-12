"""
中文：Artifact persistence layer，统一写入 JSON、JSONL 和 Markdown 报告文件。
English: Artifact persistence layer for writing JSON, JSONL, and Markdown report files.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Iterator

try:
    import fcntl
except ImportError:  # pragma: no cover - production containers and CI run on Unix-like hosts.
    fcntl = None  # type: ignore[assignment]


_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


class ArtifactStore:
    """Small local-first artifact store rooted under `artifacts/` by default."""

    def __init__(self, root: Path | str = "artifacts") -> None:
        self.root = Path(root)

    def write_json(self, relative_path: Path | str, payload: dict[str, Any]) -> Path:
        """Write a JSON artifact and return its absolute path."""
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock(relative_path):
            self._atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True))
        return path

    def write_text(self, relative_path: Path | str, content: str) -> Path:
        """Write a text artifact and return its absolute path."""
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock(relative_path):
            self._atomic_write_text(path, content)
        return path

    def write_jsonl(self, relative_path: Path | str, records: list[dict[str, Any]]) -> Path:
        """Write records as newline-delimited JSON and return the artifact path."""
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(record, sort_keys=True, default=str) for record in records]
        with self.lock(relative_path):
            self._atomic_write_text(path, "\n".join(lines) + ("\n" if lines else ""))
        return path

    def append_jsonl(self, relative_path: Path | str, records: list[dict[str, Any]]) -> Path:
        """Append records as newline-delimited JSON and return the artifact path."""
        path = self._resolve(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(record, sort_keys=True, default=str) for record in records]
        if lines:
            with self.lock(relative_path):
                with path.open("a") as file:
                    file.write("\n".join(lines) + "\n")
        return path

    @contextlib.contextmanager
    def lock(self, relative_path: Path | str) -> Iterator[None]:
        """Acquire an advisory lock for writes that may be triggered concurrently."""
        resolved_path = self._resolve(relative_path)
        lock_root = resolved_path.parent if Path(relative_path).is_absolute() else self.root
        lock_dir = lock_root / ".locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_name = _lock_name(resolved_path)
        lock_path = lock_dir / f"{lock_name}.lock"
        thread_lock = _thread_lock(lock_name)
        thread_lock.acquire()
        try:
            with lock_path.open("w") as lock_file:
                if fcntl is not None:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    if fcntl is not None:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        finally:
            thread_lock.release()

    def _resolve(self, relative_path: Path | str) -> Path:
        path = Path(relative_path)
        if path.is_absolute():
            return path
        return self.root / path

    @staticmethod
    def _atomic_write_text(path: Path, content: str) -> None:
        temp_path = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temp_path.write_text(content)
        os.replace(temp_path, path)


def _lock_name(path: Path) -> str:
    return hashlib.sha256(str(path).encode("utf-8")).hexdigest()[:32]


def _thread_lock(lock_name: str) -> threading.Lock:
    with _THREAD_LOCKS_GUARD:
        lock = _THREAD_LOCKS.get(lock_name)
        if lock is None:
            lock = threading.Lock()
            _THREAD_LOCKS[lock_name] = lock
        return lock
