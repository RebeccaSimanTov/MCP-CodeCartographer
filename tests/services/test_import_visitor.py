import ast
from src.services.repository_scanner import ImportVisitor, RepositoryScanner


def test_import_visitor_collects_imports_and_calls():
    src = """
from os import path
import json
__import__('mypkg')
import importlib
importlib.import_module('mypkg.sub')
"""
    tree = ast.parse(src)
    v = ImportVisitor(current_file="/tmp/a.py")
    v.visit(tree)
    assert 'os' in v.imports
    assert 'json' in v.imports
    assert 'mypkg' in v.imports
    assert 'mypkg.sub' in v.imports


def test__get_module_name_windows_and_unix_paths(tmp_path):
    scanner = RepositoryScanner()
    root = tmp_path / "root"
    root.mkdir()
    p = root / "pkg" / "mod.py"
    p.parent.mkdir()
    p.write_text("x=1")
    full = str(p)
    module = scanner._get_module_name(full, str(root))
    assert module.endswith("pkg.mod")
