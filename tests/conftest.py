import asyncio
import importlib
import sys
import types
import pytest

# --- Test doubles ---
class MockStorage:
    def __init__(self):
        self._graphs = {}
        self._index = {}

    def load_graph(self, graph_id):
        return self._graphs.get(graph_id)

    def update_graph_data(self, graph_id, data):
        self._graphs[graph_id] = data

    def save_report(self, graph_id, report_text):
        self._graphs.setdefault(graph_id, {})["report"] = report_text

    def save_image(self, graph_id, image_bytes):
        # simulate saving and return a fake path
        path = f"/tmp/{graph_id}.png"
        self._graphs.setdefault(graph_id, {})["image_path"] = path
        return path

    def _load_index(self):
        return self._index

    def register_scan(self, path, graph_id, timestamp="now"):
        self._index[path] = {"id": graph_id, "timestamp": timestamp}


class DummyScanner:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc

    def scan(self, path):
        if self.exc:
            raise self.exc
        # Minimal ScanResult-like object
        from src.models.schemas import ScanResult
        return self.result or ScanResult(graph_id="gid", analyzed_files=1, most_central="a", success=True)


class DummyGraphGen:
    def __init__(self):
        self.received_graph = None

    def generate_mri_view(self, graph, risk_scores=None, graph_id=None):
        self.received_graph = graph
        from src.models.schemas import MapResult
        return MapResult(success=True, node_count=graph.number_of_nodes(), edge_count=graph.number_of_edges(), message="ok", image_filename=f"{graph_id}.png", image_path=f"/tmp/{graph_id}.png")


class DummyAI:
    def __init__(self, api_key=None, to_return=None):
        self.api_key = api_key
        self._to_return = to_return or ({}, [])
        self.run_called_with = None

    async def run_mri_scan(self, g):
        self.run_called_with = g
        await asyncio.sleep(0)
        return self._to_return


# Fixture to provide a clean, patched server module for each test
@pytest.fixture
def server(monkeypatch):
    # Prevent server's stdout/stderr wrapping from interfering with pytest capture
    monkeypatch.setattr(sys, "stdout", sys.__stdout__)
    monkeypatch.setattr(sys, "stderr", sys.__stderr__)

    # Import or reload the server module so we can patch its singletons
    server_mod = importlib.import_module("server")
    importlib.reload(server_mod)

    # Attach test doubles
    storage = MockStorage()
    monkeypatch.setattr(server_mod, "storage", storage)
    monkeypatch.setattr(server_mod, "scanner", DummyScanner())
    monkeypatch.setattr(server_mod, "graph_gen", DummyGraphGen())
    monkeypatch.setattr(server_mod, "ai_analyzer", DummyAI())

    return server_mod


# Use a fresh event loop for asyncio tests
@pytest.fixture
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
