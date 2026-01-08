import pytest
import asyncio
import networkx as nx
import tempfile
from src.services.ai_analyzer import AIAnalyzer

@pytest.mark.asyncio
async def test_run_mri_scan_with_files(monkeypatch, tmp_path):
    a = AIAnalyzer()
    a.api_key = "k"

    # create temp files
    f1 = tmp_path / "mod1.py"
    f1.write_text("def x():\n    return 1\n")
    f2 = tmp_path / "mod2.py"
    f2.write_text("def y():\n    return 2\n")

    g = nx.DiGraph()
    g.add_node("mod1", file_path=str(f1))
    g.add_node("mod2", file_path=str(f2))

    async def fake_risk(fd):
        return {"mod1": 5}
    async def fake_shadows(fd):
        return [{"source":"mod1","target":"mod2","type":"db"}]

    monkeypatch.setattr(a, "_analyze_risk", fake_risk)
    monkeypatch.setattr(a, "_analyze_shadows", fake_shadows)

    risk, shadows = await a.run_mri_scan(g)
    assert isinstance(risk, dict) and "mod1" in risk
    assert isinstance(shadows, list) and shadows[0]["source"] == "mod1"
