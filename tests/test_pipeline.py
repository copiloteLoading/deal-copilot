"""Tests de la confirmation des changements de position importants (aucun appel réseau)."""

from pathlib import Path

import pytest

from copilot import memory, model, pipeline

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo_deal"
DEAL = "port-aven-kerlis"
DAY = "2026-10-29"


def sig(name, stance, quote="citation"):
    return {"actor_name": name, "organization": "", "signal_type": "information", "stance": stance,
            "strength": "strong", "source_type": "direct", "evidence_quote": quote, "confidence": 0.9}


@pytest.fixture
def conn():
    c = memory.connect(":memory:")
    memory.import_deal(c, DEMO)
    mid = memory.add_meeting(c, DEAL, "2026-10-01", "Réunion")
    memory.add_signals(c, DEAL, mid, [sig("Thomas Riou", "support"), sig("Julien Marec", "support")])
    return c


def debrief(conn, *signals):
    mid = memory.add_meeting(conn, DEAL, "2026-10-28", "Débrief")
    memory.add_signals(conn, DEAL, mid, list(signals))


def test_veto_turning_against_us_must_be_confirmed(conn):
    debrief(conn, sig("Thomas Riou", "oppose", "la banque ne suivra pas"),
            sig("Thomas Riou", "oppose", "pas à ces conditions"), sig("Julien Marec", "support"))
    changes = pipeline.pending_changes(pipeline.state(conn, DEAL, DAY), DAY)
    assert [c["actor"]["id"] for c in changes] == ["thomas_riou"]   # Julien ne change pas d'avis
    assert (changes[0]["before"], changes[0]["after"]) == ("support", "oppose")
    assert len(changes[0]["signals"]) == 2

    pipeline.confirm_change(conn, changes[0])
    assert pipeline.pending_changes(pipeline.state(conn, DEAL, DAY), DAY) == []


def test_rejected_change_no_longer_counts(conn):
    debrief(conn, sig("Thomas Riou", "oppose", "la banque ne suivra pas"),
            sig("Thomas Riou", "oppose", "pas à ces conditions"))
    st = pipeline.state(conn, DEAL, DAY)
    p_with = st.post.p
    pipeline.confirm_change(conn, pipeline.pending_changes(st, DAY)[0], stance="unknown")
    st = pipeline.state(conn, DEAL, DAY)
    assert pipeline.pending_changes(st, DAY) == []
    assert st.post.p > p_with
    assert model.STATES[int(st.post.beliefs["thomas_riou"].argmax())] == "support"


def test_small_moves_are_not_flagged(conn):
    debrief(conn, sig("Thomas Riou", "neutral", "il attend de voir"))
    assert pipeline.pending_changes(pipeline.state(conn, DEAL, DAY), DAY) == []
