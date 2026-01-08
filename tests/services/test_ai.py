import pytest
import asyncio
from src.services.ai_analyzer import AIAnalyzer
import networkx as nx

@pytest.mark.asyncio
async def test_ai_run_mri_scan_simulated(monkeypatch):
    analyzer = AIAnalyzer()
    analyzer.api_key = None
    g = nx.DiGraph()
    g.add_node("a")
    g.add_node("b")
    g.add_edge("a", "b")
    risk, links = await analyzer.run_mri_scan(g)
    assert isinstance(risk, dict)
    assert isinstance(links, list)

@pytest.mark.asyncio
async def test_ai_handles_api_errors(monkeypatch):
    analyzer = AIAnalyzer()

    async def fake_call(g):
        raise RuntimeError("api error")

    monkeypatch.setattr(analyzer, "_call_remote", fake_call, raising=False)
    g = nx.DiGraph()
    g.add_node("a")
    res = await analyzer.run_mri_scan(g)
    assert isinstance(res[0], dict) and isinstance(res[1], list)
