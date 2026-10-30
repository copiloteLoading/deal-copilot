"""Tests de la préparation de réunion avec un faux Muse Spark (aucun appel réseau)."""

from pathlib import Path

import pytest

from copilot import llm, memory, model, prepare

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo_deal"
DEAL = "port-aven-kerlis"
DAY = "2026-10-29"


def sig(name, stance, quote):
    return {"actor_name": name, "organization": "", "signal_type": "information", "stance": stance,
            "strength": "strong", "source_type": "direct", "evidence_quote": quote, "confidence": 0.9}


@pytest.fixture
def setup():
    c = memory.connect(":memory:")
    memory.import_deal(c, DEMO)
    mid = memory.add_meeting(c, DEAL, "2026-10-27", "Réunion")
    memory.add_signals(c, DEAL, mid, [sig("Sophie Lenoir", "conditional", "après le budget"),
                                      sig("Julien Marec", "support", "la plus solide")])
    return c, model.load(c, DEAL), memory.last_contact(c, DEAL)


def test_stakes_rank_the_veto_first_and_bound_the_meeting(setup):
    _, data, contact = setup
    st = prepare.stakes(data, ["julien_marec", "sophie_lenoir"], contact, DAY)
    assert st["attendees"][0]["actor"]["id"] == "sophie_lenoir"      # veto conditionnel : l'enjeu
    assert st["p_worst"] < st["p_now"] < st["p_best"]
    absent = {a["id"] for a in st["absent_vetoes"]}
    assert absent and absent <= {"thomas_riou", "marion_kervella"}  # veto absents et incertains


def test_llm_texts_are_checked(setup, monkeypatch):
    _, data, contact = setup
    sid = data.signals["sophie_lenoir"][0]["id"]
    fake = {"opening": "Tout se joue sur le budget de Baltis.", "attendees": [
        {"actor_id": "sophie_lenoir", "objective": "Obtenir l'inscription au budget",
         "question": "Quand le budget sera-t-il arrêté ?", "watch_out": "Condition posée.",
         "signal_ids": [sid, 999]},
        {"actor_id": "julien_marec", "objective": "Faire confirmer à 100 % son soutien",   # chiffre
         "question": "Q ?", "watch_out": "R.", "signal_ids": []},
        {"actor_id": "inconnu", "objective": "x", "question": "y", "watch_out": "z", "signal_ids": []}]}
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: fake)
    out = prepare.prepare(data, ["sophie_lenoir", "julien_marec"], contact, "2026-11-05", as_of=DAY)
    rows = {r["actor"]["id"]: r for r in out["attendees"]}
    assert rows["sophie_lenoir"]["by_llm"] and rows["sophie_lenoir"]["sources"][0]["quote"] == "après le budget"
    assert not rows["julien_marec"]["by_llm"]                       # texte avec un chiffre : gabarit
    assert out["opening"] and out["fallback"] is None


def test_templates_when_the_api_fails(setup, monkeypatch):
    _, data, contact = setup

    def boom(*a, **k):
        raise llm.OfflineMiss("hors ligne")

    monkeypatch.setattr(llm, "chat_json", boom)
    out = prepare.prepare(data, ["sophie_lenoir"], contact, "2026-11-05", as_of=DAY)
    assert out["fallback"] and out["attendees"][0]["objective"].startswith("Lever la condition")
