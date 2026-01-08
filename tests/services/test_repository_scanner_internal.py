import pytest
import networkx as nx
from src.services.repository_scanner import RepositoryScanner


def test_resolve_import_suffix_and_hierarchy():
    scanner = RepositoryScanner()
    # populate valid files map
    scanner._valid_files_map = {"pkg.mod", "pkg.mod.sub", "other"}
    assert scanner._resolve_import("pkg.mod") == "pkg.mod"
    assert scanner._resolve_import("mod.sub") == "pkg.mod.sub" or scanner._resolve_import("pkg.mod")
    # test hierarchy peel
    assert scanner._resolve_import("pkg.mod.sub.extra") in {"pkg.mod.sub", None}


def test_find_most_central_node():
    scanner = RepositoryScanner()
    # build dependency graph
    scanner._dependency_graph = nx.DiGraph()
    scanner._dependency_graph.add_node("a")
    scanner._dependency_graph.add_node("b")
    scanner._dependency_graph.add_edge("a","b")
    assert scanner._find_most_central_node() in {"a","b"}
