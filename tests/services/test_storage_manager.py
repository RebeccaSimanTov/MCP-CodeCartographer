import os
import json
from src.services.storage_manager import StorageManager


def test_storage_save_and_load(tmp_path, monkeypatch):
    monkeypatch.setattr(os, "getcwd", lambda: str(tmp_path))
    sm = StorageManager()

    graph = {"nodes": [{"id":"a"}], "edges": [["a","b"]]}
    gid = sm.save_scan(str(tmp_path), graph)
    assert isinstance(gid, str)

    loaded = sm.load_graph(gid)
    assert loaded["nodes"][0]["id"] == "a"

    # update_graph_data
    sm.update_graph_data(gid, {"nodes": [], "edges": []})
    assert sm.load_graph(gid)["nodes"] == []

    # save report
    rp = sm.save_report(gid, "hello")
    assert rp.endswith(f"{gid}.md")
    assert os.path.exists(rp)

    # save image
    img = sm.save_image(gid, b"bytes")
    assert img.endswith(f"{gid}.png")
    assert os.path.exists(img)

    # cleanup via save_scan again should remove old artifacts
    new_gid = sm.save_scan(str(tmp_path), {"nodes": [], "edges": []})
    assert new_gid != gid
    # old files for gid should be removed
    old_json = os.path.join(sm.dirs["graphs"], f"{gid}.json")
    assert not os.path.exists(old_json)
