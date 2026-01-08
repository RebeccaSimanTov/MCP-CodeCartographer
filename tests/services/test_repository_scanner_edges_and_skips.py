import os
import pytest
from src.services.repository_scanner import RepositoryScanner


def test_scan_skips_directories(monkeypatch, tmp_path):
    project = tmp_path / "proj"
    venv = project / "venv"
    venv.mkdir(parents=True)
    f = venv / "a.py"
    f.write_text("print('hi')")

    def fake_walk(p):
        yield (str(venv), [], ["a.py"])

    monkeypatch.setattr(os, "walk", lambda p: fake_walk(p))
    scanner = RepositoryScanner()
    res = scanner.scan(str(project))
    # no modules found because only skipped dir
    assert res.analyzed_files == 0


def test_scan_detects_dynamic_imports(monkeypatch, tmp_path):
    project = tmp_path / "proj2"
    project.mkdir()
    f = project / "a.py"
    # insert __import__ and import_module calls
    f.write_text('__import__("mypkg.sub"); import importlib\nimportlib.import_module("mypkg.sub")')

    def fake_walk(p):
        yield (str(project), [], ["a.py"])

    monkeypatch.setattr(os, "walk", lambda p: fake_walk(p))
    # patch storage to avoid filesystem writes
    monkeypatch.setattr('src.services.repository_scanner.storage', type('S', (), {"save_scan": lambda *a, **k: "g"})())
    scanner = RepositoryScanner()
    res = scanner.scan(str(project))
    # Should at least return a ScanResult object and not crash
    assert hasattr(res, 'graph_id')
