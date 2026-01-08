import pytest
import asyncio
import httpx
from src.services.ai_analyzer import AIAnalyzer


def test__clean_json_text_variants():
    a = AIAnalyzer()
    fenced = '```json\n{"a": 1}\n```'
    assert a._clean_json_text(fenced).strip().startswith('{')

    generic = '```\n{"b":2}\n```'
    assert a._clean_json_text(generic).strip().startswith('{')

    plain = '{"c":3}'
    assert a._clean_json_text(plain).strip() == plain


@pytest.mark.asyncio
async def test__call_gemini_403_returns_default(monkeypatch):
    a = AIAnalyzer()
    a.api_key = "k"

    class FakeResp:
        def raise_for_status(self):
            request = None
            response = type("R", (), {"status_code": 403})()
            raise httpx.HTTPStatusError("err", request=request, response=response)

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, json=None):
            return FakeResp()

    monkeypatch.setattr('httpx.AsyncClient', lambda *a, **k: FakeClient())
    async def _noop_sleep(*a, **k):
        return None
    monkeypatch.setattr(asyncio, 'sleep', _noop_sleep)

    res = await a._call_gemini("prompt", default_val={"x": 0})
    assert res == {"x": 0}


def test__extract_smart_context_variants():
    a = AIAnalyzer()
    content = '''"""Doc"""\nimport os\nfrom sys import path\nCONSTANT = 1\nclass A:\n    pass\ndef f():\n    execute(query)\n    redis.publish('x')\n    os.getenv('Y')\n'''
    out = a._extract_smart_context(content)
    # Should include docstring, import, class/def lines and keywords
    assert 'Doc' in out
    assert 'import os' in out
    assert 'class A' in out
    assert 'execute(' in out


def test__extract_smart_context_invalid_syntax():
    a = AIAnalyzer()
    bad = 'def f(:\n    pass'
    out = a._extract_smart_context(bad)
    assert '...[SNIPPED]...' in out or len(out) < 500


@pytest.mark.asyncio
async def test__analyze_risk_and_shadows_calls_call_gemini(monkeypatch):
    a = AIAnalyzer()
    # Make _call_gemini return deterministic results
    async def fake_call(self, prompt, default_val):
        if isinstance(default_val, dict):
            return {'mod': 5}
        return [{'source': 'A', 'target': 'B', 'type': 'db'}]

    monkeypatch.setattr(AIAnalyzer, '_call_gemini', fake_call)

    risk = await a._analyze_risk({'m': 'x'})
    shadows = await a._analyze_shadows({'m': 'x'})
    assert isinstance(risk, dict) and risk.get('mod') == 5
    assert isinstance(shadows, list) and shadows[0]['source'] == 'A'


@pytest.mark.asyncio
async def test__call_gemini_malformed_json_falls_back(monkeypatch):
    a = AIAnalyzer()
    a.api_key = "k"
    a.max_retries = 1

    class FakeRespBad:
        def raise_for_status(self):
            return None
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '```json {not: valid} ```'}]}}]}

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, json=None):
            return FakeRespBad()

    monkeypatch.setattr('httpx.AsyncClient', lambda *a, **k: FakeClient())
    async def _noop_sleep(*a, **k):
        return None
    monkeypatch.setattr(asyncio, 'sleep', _noop_sleep)

    res = await a._call_gemini("prompt", default_val={"x": 0})
    assert res == {"x": 0}
