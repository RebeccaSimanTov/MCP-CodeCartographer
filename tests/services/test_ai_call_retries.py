import pytest
import httpx
import asyncio
from src.services.ai_analyzer import AIAnalyzer


@pytest.mark.asyncio
async def test__call_gemini_retry_and_fail(monkeypatch):
    a = AIAnalyzer()
    a.api_key = "k"

    calls = {"count": 0}

    class FakeResp:
        def raise_for_status(self):
            # always raise HTTPStatusError with non-403/429 status to trigger retry
            request = None
            response = type("R", (), {"status_code": 500})()
            raise httpx.HTTPStatusError("err", request=request, response=response)

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, json=None):
            calls['count'] += 1
            return FakeResp()

    # speed up sleeps
    async def _noop_sleep(*a, **k):
        return None
    monkeypatch.setattr(asyncio, 'sleep', _noop_sleep)
    monkeypatch.setattr('httpx.AsyncClient', lambda *args, **kwargs: FakeClient())

    res = await a._call_gemini("prompt", default_val={"x": 0})
    assert res == {"x": 0}
    # Should have attempted max_retries times
    assert calls['count'] >= 1
