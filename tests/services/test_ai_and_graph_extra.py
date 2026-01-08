import pytest
import asyncio
import networkx as nx
from src.services.ai_analyzer import AIAnalyzer
from src.services.graph_generator import GraphGenerator


@pytest.mark.asyncio
async def test_run_mri_scan_with_files_and_monkeypatched_analyzers(tmp_path, monkeypatch):
    # Create a temp python file to be discovered by run_mri_scan
    f = tmp_path / "mod_a.py"
    f.write_text('''"""Module A"""\nimport os\ndef foo():\n    pass\n''')

    g = nx.DiGraph()
    g.add_node('mod_a', file_path=str(f))

    a = AIAnalyzer()
    a.api_key = "k"

    async def fake_risk(self, files_data):
        return {k: 3 for k in files_data.keys()}

    async def fake_shadows(self, files_data):
        return [{"source": "mod_a", "target": "mod_b", "type": "db"}]

    monkeypatch.setattr(AIAnalyzer, '_analyze_risk', fake_risk)
    monkeypatch.setattr(AIAnalyzer, '_analyze_shadows', fake_shadows)

    risks, shadows = await a.run_mri_scan(g)
    assert isinstance(risks, dict) and 'mod_a' in risks
    assert isinstance(shadows, list) and shadows[0]["source"] == 'mod_a'


def test_graph_generator_handles_in_degree_exception(monkeypatch, tmp_path):
    from src import services as services_pkg
    gg = GraphGenerator()

    # Build a small graph
    g = nx.DiGraph()
    g.add_node('a'); g.add_node('b'); g.add_edge('a', 'b', type='explicit')

    # Force in_degree_centrality to raise to hit the except branch
    monkeypatch.setattr(services_pkg.graph_generator.nx, 'in_degree_centrality', lambda g: (_ for _ in ()).throw(Exception('boom')))

    # Monkeypatch storage.save_image to avoid disk writes
    monkeypatch.setattr('src.services.graph_generator.storage.save_image', lambda gid, b: str(tmp_path / f"{gid}.png"))

    res = gg.generate_mri_view(g, risk_scores={}, graph_id='t42')
    assert res.success is True
