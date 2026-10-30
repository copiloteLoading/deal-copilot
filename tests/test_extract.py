"""Tests d'extract.py sans appel réseau : le modèle est remplacé par une réponse écrite à la main."""

from pathlib import Path

import pytest

from copilot import extract, llm, memory

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo_deal"
TEXT = (DEMO / "debriefs" / "2026-10-27_consortium.txt").read_text(encoding="utf-8")


def signal(name, quote, **kw):
    base = {"actor_name": name, "entity_kind": "person", "organization": "", "role": "",
            "signal_type": "support", "stance": "support", "strength": "strong",
            "source_type": "direct", "description": "", "evidence_quote": quote, "confidence": 0.9}
    return {**base, **kw}


FAKE = {
    "summary": "Réunion positive.",
    "signals": [
        signal("Julien Marec", "la plus solide techniquement"),
        # apostrophe typographique et espaces en trop : doit être accepté
        signal("Thomas Riou", "ça fait  maintenant six semaines qu’on ne l’a pas vu",
               signal_type="risk", stance="unknown", source_type="reported"),
        # citation inventée : doit être écartée
        signal("Sophie Lenoir", "nous validerons sans condition", confidence=1.4),
        signal("Sophie Lenoir", "elle veut étaler sur quatre ans au lieu de trois",
               signal_type="condition", stance="conditional", confidence=1.4),
    ],
    "next_steps": [], "open_questions": [],
}


@pytest.fixture
def conn(monkeypatch):
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: {**FAKE, "signals": list(FAKE["signals"])})
    c = memory.connect(":memory:")
    memory.import_deal(c, DEMO)
    return c


def test_quotes_are_checked(conn):
    result = extract.extract(TEXT, conn, "port-aven-kerlis")
    kept = [s["evidence_quote"] for s in result["signals"]]
    assert len(kept) == 3
    assert [s["evidence_quote"] for s in result["rejected"]] == ["nous validerons sans condition"]


def test_one_word_quotes_prove_nothing():
    notes = "Participants\nThomas Riou : « pas de financement tant que l'étude n'est pas validée »"
    kept, rejected = extract.check_signals(notes, [{"evidence_quote": "Participants", "confidence": 0.5},
                                                   {"evidence_quote": "pas de financement", "confidence": 0.9}])
    assert [s["evidence_quote"] for s in kept] == ["pas de financement"]
    assert [s["evidence_quote"] for s in rejected] == ["Participants"]


def test_confidence_is_clamped(conn):
    result = extract.extract(TEXT, conn, "port-aven-kerlis")
    assert all(0 <= s["confidence"] <= 1 for s in result["signals"])


def test_context_lists_known_names_without_positions(conn):
    ctx = extract._deal_context(conn, "port-aven-kerlis")
    assert "Sophie Lenoir" in ctx and "la DAF de Baltis" in ctx
    assert "support" not in ctx and "veto" not in ctx.lower()


def test_extract_and_store(conn):
    result = extract.extract_and_store(conn, "port-aven-kerlis", "2026-10-28", TEXT, "Test")
    assert result["unresolved"] == []
    contact = memory.last_contact(conn, "port-aven-kerlis")
    assert contact["julien_marec"] == "2026-10-28"
    assert contact["thomas_riou"] is None
