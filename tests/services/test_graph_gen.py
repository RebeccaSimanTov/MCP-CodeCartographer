import pytest
import matplotlib
# Use Agg backend for headless test envs to avoid Tk dependency
matplotlib.use("Agg")
import networkx as nx
from src.services.graph_generator import GraphGenerator


def test_graph_generator_renders_and_persists(tmp_path, monkeypatch):
    gg = GraphGenerator()
    g = nx.DiGraph()
    g.add_node("n1")
    g.add_node("n2")
    g.add_edge("n1", "n2")

    saved = {}
    def fake_save_image(gid, bytes_blob):
        path = tmp_path / f"{gid}.png"
        with open(path, "wb") as f:
            f.write(bytes_blob)
        saved['path'] = str(path)
        saved['size'] = path.stat().st_size
        return str(path)

    monkeypatch.setattr('src.services.graph_generator.storage.save_image', fake_save_image)
    res = gg.generate_mri_view(g, risk_scores={"n1": 9}, graph_id="t1")
    assert res.success is True
    assert res.image_path == saved['path']
    assert saved['size'] > 0


def test_graph_generator_handles_empty_graph(monkeypatch):
    gg = GraphGenerator()
    g = nx.DiGraph()
    res = gg.generate_mri_view(g, risk_scores={}, graph_id="empty")
    assert res.node_count == 0
    assert res.edge_count == 0


def test_generate_mri_view_edge_styles(monkeypatch, tmp_path):
    gg = GraphGenerator()
    g = nx.DiGraph()
    # Create layers a->b->c and explicit a->c to force large y-gap between a and c
    g.add_node("a"); g.add_node("b"); g.add_node("c")
    g.add_edge("a","b", type="explicit")
    g.add_edge("b","c", type="explicit")
    g.add_edge("a","c", type="explicit")
    # Add a hidden link
    g.add_edge("b","a", type="hidden")

    saved = {}
    def fake_save_image(gid, bytes_blob):
        path = tmp_path / f"{gid}.png"
        with open(path, "wb") as f:
            f.write(bytes_blob)
        saved['path'] = str(path)
        saved['size'] = path.stat().st_size
        return str(path)

    monkeypatch.setattr('src.services.graph_generator.storage.save_image', fake_save_image)

    res = gg.generate_mri_view(g, risk_scores={"a": 9, "b": 2}, graph_id="t2")
    assert res.success is True
    assert saved['size'] > 0


def test_generate_alias_and_format_label():
    gg = GraphGenerator()
    g = nx.DiGraph(); g.add_node("x.y_z")
    assert gg._format_label("pkg.mod_sub") == "pkg.\nmod_\nsub"
    # Alias
    r = gg.generate(g, risk_scores={})
    assert r.node_count == 1
