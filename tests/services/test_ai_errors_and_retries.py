import pytest
import asyncio
import httpx
from src.services.ai_analyzer import AIAnalyzer


@pytest.mark.asyncio
async def test__call_gemini_429_retries_returns_default(monkeypatch):
    a = AIAnalyzer()
    a.api_key = "k"
    a.max_retries = 2

    class FakeResp:
        def raise_for_status(self):
            request = None
            response = type("R", (), {"status_code": 429})()
            raise httpx.HTTPStatusError("err", request=request, response=response)

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, json=None):
            return FakeResp()

    monkeypatch.setattr('httpx.AsyncClient', lambda *args, **kwargs: FakeClient())
    # patch sleep to be a no-op to speed tests
    async def _noop_sleep(*a, **k):
        return None
    monkeypatch.setattr(asyncio, 'sleep', _noop_sleep)

    res = await a._call_gemini("prompt", default_val={"x": 0})
    assert res == {"x": 0}


@pytest.mark.asyncio
async def test__call_gemini_exception_then_success(monkeypatch):
    a = AIAnalyzer()
    a.api_key = "k"
    a.max_retries = 3

    calls = {"n": 0}

    class FakeRespGood:
        def raise_for_status(self):
            return None
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"ok": 1}'}]}}]}

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, json=None):
            calls['n'] += 1
            if calls['n'] == 1:
                raise Exception("network fail")
            return FakeRespGood()

    monkeypatch.setattr('httpx.AsyncClient', lambda *args, **kwargs: FakeClient())
    async def _noop_sleep(*a, **k):
        return None
    monkeypatch.setattr(asyncio, 'sleep', _noop_sleep)
    res = await a._call_gemini("prompt", default_val={"x": 0})
    assert res == {"ok": 1}


# test__extract_smart_context_invalid_syntax removed — consolidated in tests/services/test_ai_clean_and_call_extra.py
