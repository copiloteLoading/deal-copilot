"""Tests de la prévision par Muse Spark avec un faux modèle (aucun appel réseau)."""

from pathlib import Path

from copilot import forecast, llm, memory

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo_deal"
DEAL = "port-aven-kerlis"


def test_forecast_averages_independent_draws(monkeypatch):
    seen = []

    def fake(messages, name, schema, cache_tag=None, **k):
        seen.append(cache_tag)
        p = {None: 0.30, "draw1": 0.40, "draw2": 1.7}[cache_tag]       # 1.7 : borné à 1
        return {"probability": p, "rationale": f"tirage {cache_tag}"}

    monkeypatch.setattr(llm, "chat_json", fake)
    conn = memory.connect(":memory:")
    memory.import_deal(conn, DEMO)
    deal = memory.get_deal(conn, DEAL)
    out = forecast.forecast(deal, forecast.texts_until(conn, DEAL))
    assert sorted(seen, key=str) == sorted([None, "draw1", "draw2"], key=str)   # trois tirages distincts
    assert abs(out["p"] - (0.30 + 0.40 + 1.0) / 3) < 1e-9
    assert out["rationale"] == "tirage None"                                   # le premier explique


def test_texts_include_answers_in_order():
    conn = memory.connect(":memory:")
    memory.import_deal(conn, DEMO)
    first = memory.meetings(conn, DEAL)[0]["id"]
    mid = memory.add_meeting(conn, DEAL, "2026-10-29", "Answer", "Question: x\nAnswer: y")
    texts = forecast.texts_until(conn, DEAL)
    assert texts[-1] == ("2026-10-29", "Question: x\nAnswer: y")
    assert len(forecast.texts_until(conn, DEAL, first)) == 1 and mid > first
    # des notes prises en photo après coup, datées d'avant : comptées à leur date
    late = memory.add_meeting(conn, DEAL, "2026-10-20", "Photo", "notes")
    assert ("2026-10-20", "notes") in forecast.texts_until(conn, DEAL, mid)
    assert forecast.texts_until(conn, DEAL, late)[-1] == ("2026-10-20", "notes")
