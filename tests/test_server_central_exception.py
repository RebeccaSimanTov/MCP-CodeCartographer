import pytest
import networkx as nx
from src.models.schemas import AIAnalysis


@pytest.mark.asyncio
async def test_run_architectural_mri_handles_degree_centrality_exception(server, monkeypatch):
    graph_id = "g_exc"
    nodes = [{"id": "a"}, {"id": "b"}]
    edges = [("a","b")]
    server.storage.update_graph_data(graph_id, {"nodes": nodes, "edges": edges})

    class DummyAI:
        api_key = None
        async def run_mri_scan(self, g):
            return ({}, [])

    monkeypatch.setattr(server, "ai_analyzer", DummyAI())
    # Force degree_centrality to raise
    import src.services.graph_generator as gg_mod
    monkeypatch.setattr(gg_mod.nx, 'degree_centrality', lambda g: (_ for _ in ()).throw(Exception('boom')), raising=False)

    out = await server.run_architectural_mri(graph_id, force_refresh=True)
    assert isinstance(out, AIAnalysis)
    # since central_node failed, module should be graph_id fallback
    assert out.module == graph_id
    assert out.dependencies == [] and out.used_by == []
