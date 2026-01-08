import pytest
import networkx as nx

from src.models.schemas import ScanResult, MapResult, AIAnalysis, ErrorModel

# All tests take `server` fixture (provides patched singletons)

def test_scan_repository_happy(server, monkeypatch):
    # Create a valid ScanResult (schema requires path, analyzed_files, most_central)
    expected = ScanResult(analyzed_files=3, most_central="modA", path=".", success=True, graph_id="g123")
    class S:
        def scan(self, path): return expected
    monkeypatch.setattr(server, "scanner", S())
    res = server.scan_repository(path=".")
    assert isinstance(res, ScanResult)
    assert res.graph_id == "g123"


def test_scan_repository_exception(server, monkeypatch):
    class S:
        def scan(self, path): raise RuntimeError("boom")
    monkeypatch.setattr(server, "scanner", S())
    with pytest.raises(RuntimeError):
        server.scan_repository(path=".")


def test_generate_quick_map_not_found(server):
    res = server.generate_quick_map("no-such-id")
    assert isinstance(res, MapResult)
    assert not res.success
    assert "not found" in (res.message or "").lower()


def test_generate_quick_map_structural(server):
    graph_id = "g1"
    nodes = [{"id": "a"}, {"id": "b"}]
    edges = [("a", "b")]
    server.storage.update_graph_data(graph_id, {"nodes": nodes, "edges": edges})
    res = server.generate_quick_map(graph_id)
    assert isinstance(res, MapResult)
    assert res.success
    assert res.node_count == 2
    assert res.edge_count == 1


def test_generate_quick_map_with_mri(server):
    graph_id = "g2"
    nodes = [{"id": "a"}, {"id": "b"}]
    edges = [("a", "b")]
    hidden = [{"source": "b", "target": "a", "type": "db"}]
    server.storage.update_graph_data(graph_id, {"nodes": nodes, "edges": edges, "ai_analysis": {"hidden_links": hidden}})
    ggen = server.graph_gen
    res = server.generate_quick_map(graph_id)
    assert res.success
    assert any(edge for edge in ggen.received_graph.edges() if edge == ("b", "a"))
    assert ggen.received_graph["b"]["a"].get("type") == "hidden"


@pytest.mark.asyncio
async def test_run_architectural_mri_not_found(server):
    out = await server.run_architectural_mri("no-graph")
    assert isinstance(out, AIAnalysis)
    assert out.meta["graph_found"] == False or any(isinstance(e, ErrorModel) for e in out.errors)


@pytest.mark.asyncio
async def test_run_architectural_mri_cache_hit(server, monkeypatch):
    graph_id = "g_cache"
    cached = {"module_analysis": {"module": "a", "dependencies": [], "used_by": [], "analysis": "cached", "simulated": False, "meta": {}, "errors": []}}
    nodes = [{"id": "a"}, {"id": "b"}]
    edges = [("a", "b")]
    server.storage.update_graph_data(graph_id, {"nodes": nodes, "edges": edges, "ai_analysis": cached})
    out = await server.run_architectural_mri(graph_id, force_refresh=False)
    assert isinstance(out, AIAnalysis)
    assert out.analysis == "cached"


@pytest.mark.asyncio
async def test_run_architectural_mri_cache_miss_and_save(server, monkeypatch):
    graph_id = "g_new"
    nodes = [{"id": "center"}, {"id": "leaf"}]
    edges = [("center", "leaf")]
    server.storage.update_graph_data(graph_id, {"nodes": nodes, "edges": edges})

    class Dummy:
        api_key = "key"
        async def run_mri_scan(self, g):
            return ({"center": 9}, [{"source":"center","target":"leaf","type":"db"}])

    monkeypatch.setattr(server, "ai_analyzer", Dummy())
    out = await server.run_architectural_mri(graph_id, force_refresh=True)
    assert isinstance(out, AIAnalysis)
    assert out.module == "center" or out.module == graph_id
    data = server.storage.load_graph(graph_id)
    assert "ai_analysis" in data
    assert "report" in data


def test_list_available_graphs_empty(server):
    server.storage._index = {}
    res = server.list_available_graphs()
    assert "No scans found" in res


def test_list_available_graphs_populated(server):
    server.storage.register_scan("pathA", "gidA", timestamp="t1")
    out = server.list_available_graphs()
    assert "gidA" in out and "pathA" in out


def test_get_graph_stats_basic(server):
    g_id = "stats_g"
    nodes = [{"id":"n1"}, {"id":"n2"}, {"id":"n3"}]
    edges = [("n1","n2"), ("n2","n3")]
    server.storage.update_graph_data(g_id, {"nodes": nodes, "edges": edges})
    s = server.get_graph_stats(g_id)
    assert "Total Modules" in s and "Total Connections" in s


def test_get_risk_report_no_ai(server):
    g_id = "no_ai"
    server.storage.update_graph_data(g_id, {"nodes": [], "edges": []})
    assert "No AI analysis found" in server.get_risk_report(g_id)


def test_get_risk_report_with_high_risks(server):
    g_id = "with_ai"
    data = {"nodes": [], "edges": [], "ai_analysis": {"risk_scores": {"a": 6, "b": 4}}}
    server.storage.update_graph_data(g_id, data)
    out = server.get_risk_report(g_id)
    assert "- 🔴 **a** (Score: 6/10)" in out
    assert "- 🔴 **b**" not in out


def test_get_module_context_edge_cases(server):
    assert "Graph not found" in server.get_module_context("no_graph", "x")
    g_id = "ctx"
    nodes = [{"id":"m1"}, {"id":"m2"}]
    edges = [("m2","m1")]
    server.storage.update_graph_data(g_id, {"nodes": nodes, "edges": edges})
    assert "not found" in server.get_module_context(g_id, "mX")
    out = server.get_module_context(g_id, "m1")
    assert "Risk Score" in out
