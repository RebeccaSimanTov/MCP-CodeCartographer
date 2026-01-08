import os
import json
import pytest
from src.services.storage_manager import StorageManager


def test_load_index_handles_bad_json(tmp_path, monkeypatch):
    # Create base dir with invalid index.json
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    base = tmp_path / "mcp_storage"
    base.mkdir()
    idx = base / "index.json"
    idx.write_text("not-json")

    sm = StorageManager()
    # Should gracefully ignore invalid json and have empty index
    assert sm._index == {}


def test_delete_artifacts_handles_remove_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    sm = StorageManager()
    # Create fake files
    gid = "x1"
    for dtype, dpath in sm.dirs.items():
        os.makedirs(dpath, exist_ok=True)
        ext = ".json" if dtype == "graphs" else (".png" if dtype=="images" else ".md")
        p = os.path.join(dpath, f"{gid}{ext}")
        with open(p, "w", encoding="utf-8") as f:
            f.write("x")

    # Make os.remove raise
    monkeypatch.setattr(os, "remove", lambda p: (_ for _ in ()).throw(Exception("rm fail")))
    # Should not raise
    sm._delete_artifacts(gid)
