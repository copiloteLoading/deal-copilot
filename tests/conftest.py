"""Les tests n'appellent jamais le réseau : mode hors ligne et caches vides pour chacun."""

import pytest

from copilot import llm


@pytest.fixture(autouse=True)
def no_network(monkeypatch, tmp_path):
    monkeypatch.setenv("LLM_PROVIDER", "offline")
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(llm, "DEMO_CACHE_DIR", tmp_path / "demo_cache")
