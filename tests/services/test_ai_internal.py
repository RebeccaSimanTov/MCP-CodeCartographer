import pytest
import asyncio
import json
from src.services.ai_analyzer import AIAnalyzer
import httpx


# test__clean_json_text_variants removed — consolidated in tests/services/test_ai_clean_and_call_extra.py


# test__extract_smart_context_basic duplicated by
# tests/services/test_ai_clean_and_call_extra.py::test__extract_smart_context_variants
# Removed duplicate here.


@pytest.mark.asyncio
async def test__call_gemini_success(monkeypatch):
    a = AIAnalyzer()
    # Fake API key to build url
    a.api_key = "k"

    class FakeResp:
        def raise_for_status(self):
            return None
        def json(self):
            return {"candidates": [{"content": {"parts": [{"text": '{"m": 1}' }]}}]}

    class FakeClient:
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc, tb):
            return False
        async def post(self, url, json=None):
            return FakeResp()

    monkeypatch.setattr('httpx.AsyncClient', lambda *args, **kwargs: FakeClient())
    res = await a._call_gemini("prompt", default_val={"x": 0})
    assert res == {"m": 1}


# test__call_gemini_403 removed — consolidated in tests/services/test_ai_clean_and_call_extra.py
