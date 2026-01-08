import pytest
import networkx as nx
from src.services import graph_generator as gg_mod
from src.services.graph_generator import GraphGenerator


def test_layout_fallback_and_edge_style(monkeypatch, tmp_path):
    # Force topological_generations to raise so we take the spring_layout fallback
    def _raise_topo(g):
        raise Exception('boom')
    monkeypatch.setattr(gg_mod.nx, "topological_generations", _raise_topo)
    # Make spring_layout return a pos with a missing/None entry to trigger the 'except' branch in edge styling
    def fake_spring(g, k=None, iterations=None):
        return {"a": (0, 0), "b": None, "c": (0, -20)}
    monkeypatch.setattr(gg_mod.nx, "spring_layout", fake_spring)

    # Capture draw_networkx_edges call to inspect color/style used in except branch
    captured = {}
    def fake_draw_networkx_edges(graph, pos, edgelist, edge_color, style, width, alpha, connectionstyle, arrows, arrowsize, arrowstyle, min_source_margin, min_target_margin, ax):
        captured['color'] = edge_color
        captured['style'] = style
        return None

    monkeypatch.setattr(gg_mod.nx, "draw_networkx_edges", fake_draw_networkx_edges)
    # Avoid numpy errors in draw_networkx_nodes and labels for our injected pos (nodes with None)
    monkeypatch.setattr(gg_mod.nx, "draw_networkx_nodes", lambda *a, **k: None)
    monkeypatch.setattr(gg_mod.nx, "draw_networkx_labels", lambda *a, **k: None)

    g = nx.DiGraph()
    g.add_node("a"); g.add_node("b"); g.add_node("c")
    g.add_edge("a", "b", type="explicit")
    g.add_edge("a", "c", type="explicit")

    gg = GraphGenerator()
    # monkeypatch save_image to a no-op
    monkeypatch.setattr('src.services.graph_generator.storage.save_image', lambda gid, b: str(tmp_path / f"{gid}.png"))

    res = gg.generate_mri_view(g, risk_scores={"a": 25}, graph_id="t3")
    assert res.success
    # ensure that in the except-in-edge-style branch we saw fallback color 'gray'
    assert captured.get('color') == 'gray' or captured.get('style') in ("solid",)
