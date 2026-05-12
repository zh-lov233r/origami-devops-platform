"""
中文：ArtifactStore 单元测试，验证 JSON、JSONL 和文本 artifact 可以稳定落盘。
English: Unit tests for ArtifactStore ensuring JSON, JSONL, and text artifacts persist reliably.
"""

import json
from pathlib import Path

from origami.persistence.artifact_store import ArtifactStore


def test_artifact_store_writes_json_jsonl_and_text(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path)

    json_path = store.write_json("reports/example.json", {"ok": True})
    jsonl_path = store.write_jsonl("events/example.jsonl", [{"step": 0}, {"step": 1}])
    store.append_jsonl("events/example.jsonl", [{"step": 2}])
    text_path = store.write_text("reports/example.md", "# Example\n")

    assert json.loads(json_path.read_text()) == {"ok": True}
    assert jsonl_path.read_text().splitlines() == [
        '{"step": 0}',
        '{"step": 1}',
        '{"step": 2}',
    ]
    assert text_path.read_text() == "# Example\n"


def test_artifact_store_locks_absolute_paths_next_to_target(tmp_path: Path) -> None:
    store = ArtifactStore(".")
    output_path = tmp_path / "absolute.json"

    store.write_json(output_path, {"ok": True})

    assert json.loads(output_path.read_text()) == {"ok": True}
    assert (tmp_path / ".locks").exists()


def test_artifact_store_locks_relative_paths_under_root(tmp_path: Path) -> None:
    store = ArtifactStore(tmp_path / "artifacts")

    path = store.write_json("reports/example.json", {"ok": True})

    assert path == tmp_path / "artifacts/reports/example.json"
    assert not (tmp_path / "artifacts/artifacts").exists()
    assert (tmp_path / "artifacts/.locks").exists()
