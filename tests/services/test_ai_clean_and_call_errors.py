import pytest
import asyncio
import httpx
from src.services.ai_analyzer import AIAnalyzer


@pytest.mark.asyncio
async def test__call_gemini_handles_fenced_json(monkeypatch):
    a = AIAnalyzer()
    a.api_key = "k"

    class FakeResp:
        def raise_for_status(self):
            return None
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '```json {"x": 5} ```'}]}}]}

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): return False
        async def post(self, url, json=None): return FakeResp()

    monkeypatch.setattr('httpx.AsyncClient', lambda *args, **kwargs: FakeClient())
    res = await a._call_gemini("prompt", default_val={"fail": True})
    assert res == {"x": 5}


@pytest.mark.asyncio
async def test__call_gemini_malformed_json_returns_default(monkeypatch):
    a = AIAnalyzer()
    a.api_key = "k"

    class FakeResp:
        def raise_for_status(self):
            return None
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": 'not json'}]}}]}

    class FakeClient:
        async def __aenter__(self): return self
        async def __aexit__(self, exc_type, exc, tb): return False
        async def post(self, url, json=None): return FakeResp()

    monkeypatch.setattr('httpx.AsyncClient', lambda *args, **kwargs: FakeClient())
    # max_retries small for test speed
    a.max_retries = 1
    res = await a._call_gemini("prompt", default_val={"x": 0})
    assert res == {"x": 0}
