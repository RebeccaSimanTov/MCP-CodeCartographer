import os
import pytest
from src.services.repository_scanner import RepositoryScanner
from src.models.schemas import ScanResult


def test_scanner_scan_with_fake_files(monkeypatch, tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    f1 = project / "a.py"
    f1.write_text("import os\nfrom sys import path\n")
    f2 = project / "b.py"
    f2.write_text("class A: pass\n")

    def fake_walk(path):
        yield (str(project), [], ["a.py", "b.py"])

    monkeypatch.setattr(os, "walk", lambda p: fake_walk(p))
    scanner = RepositoryScanner()
    # Patch module-level storage used by RepositoryScanner
    monkeypatch.setattr('src.services.repository_scanner.storage', type("S", (), {"update_graph_data": lambda *a, **k: None, "save_scan": lambda *a, **k: "g1"})())
    res = scanner.scan(str(project))
    assert isinstance(res, ScanResult)
    assert hasattr(res, "graph_id")


def test_scanner_handles_unreadable_file(monkeypatch, tmp_path):
    project = tmp_path / "proj2"
    project.mkdir()
    f = project / "c.py"
    f.write_text("import something\n")

    def fake_open(*a, **k):
        raise IOError("can't read")

    monkeypatch.setattr("builtins.open", fake_open)
    scanner = RepositoryScanner()
    res = scanner.scan(str(project))
    assert isinstance(res, ScanResult)
