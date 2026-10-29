"""Tests du modèle par acteur et du moteur de décision (aucun appel réseau)."""

from pathlib import Path

import numpy as np
import pytest

from copilot import decision, memory, model

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo_deal"
DEAL = "port-aven-kerlis"


def sig(name, stance, quote="citation", strength="strong", source="direct", conf=0.9,
        signal_type="information"):
    return {"actor_name": name, "organization": "", "signal_type": signal_type, "stance": stance,
            "strength": strength, "source_type": source, "evidence_quote": quote, "confidence": conf}


@pytest.fixture
def conn():
    c = memory.connect(":memory:")
    memory.import_deal(c, DEMO)
    return c


def add(conn, day, *signals):
    mid = memory.add_meeting(conn, DEAL, day)
    memory.add_signals(conn, DEAL, mid, list(signals))
    return mid


def test_no_signal_gives_the_prior(conn):
    data = model.load(conn, DEAL)
    P = model.params()
    assert np.allclose(model.belief(data, "julien_marec", "2026-10-29"), P["prior"])
    # le régulateur a son propre a priori
    assert np.allclose(model.belief(data, "marion_kervella", "2026-10-29"),
                       P["prior_by_org_type"]["regulator"])


def test_signals_move_the_belief_in_the_right_direction(conn):
    add(conn, "2026-10-27", sig("Julien Marec", "support"), sig("Yann Le Goff", "oppose"))
    data = model.load(conn, DEAL)
    prior = np.array(model.params()["prior"])
    assert model.belief(data, "julien_marec", "2026-10-27")[0] > prior[0]
    assert model.belief(data, "yann_le_goff", "2026-10-27")[2] > prior[2]


def test_weak_signal_moves_less_than_strong(conn):
    add(conn, "2026-10-27", sig("Julien Marec", "support", strength="strong"),
        sig("Yann Le Goff", "support", strength="weak"))
    data = model.load(conn, DEAL)
    assert (model.belief(data, "julien_marec", "2026-10-27")[0]
            > model.belief(data, "yann_le_goff", "2026-10-27")[0])


def test_silence_brings_the_belief_back_to_the_prior(conn):
    add(conn, "2026-09-01", sig("Julien Marec", "support"))
    data = model.load(conn, DEAL)
    prior = np.array(model.params()["prior"])
    soon = model.belief(data, "julien_marec", "2026-09-08")
    late = model.belief(data, "julien_marec", "2027-03-01")
    assert abs(late - prior).sum() < abs(soon - prior).sum()


def test_veto_rule_and_interval(conn):
    data = model.load(conn, DEAL)
    base = model.posterior(data, "2026-10-29")
    assert 0 <= base.low <= base.p <= base.high <= 1
    blocked = model.simulate(data, {"sophie_lenoir": "oppose"}, "2026-10-29")
    won = model.simulate(data, {"sophie_lenoir": "support"}, "2026-10-29")
    assert blocked.p < base.p < won.p
    # un acteur sans veto pèse moins qu'un veto
    assert (model.simulate(data, {"yann_le_goff": "oppose"}, "2026-10-29").p > blocked.p)


def test_explain_measures_each_signal(conn):
    add(conn, "2026-10-27", sig("Julien Marec", "support"), sig("Sophie Lenoir", "oppose"))
    data = model.load(conn, DEAL)
    ids = [s["id"] for sigs in data.signals.values() for s in sigs]
    moves = {m["signal"]["actor_id"]: m["delta"] for m in model.explain(data, ids, "2026-10-27")}
    assert moves["julien_marec"] > 0 > moves["sophie_lenoir"]


def test_deadlines_do_not_move_positions(conn):
    add(conn, "2026-10-27", sig("Sophie Lenoir", "oppose", signal_type="deadline"))
    data = model.load(conn, DEAL)
    assert data.signals["sophie_lenoir"] == []


def test_questions_target_uncertain_vetoes(conn):
    add(conn, "2026-10-27", sig("Julien Marec", "support"), sig("Claire Dantec", "support"),
        sig("Yann Le Goff", "support"), sig("Sophie Lenoir", "conditional"))
    data = model.load(conn, DEAL)
    qs = decision.rank_questions(data, memory.last_contact(conn, DEAL), "2026-10-29")
    assert 1 <= len(qs) <= 2
    assert all(q["actor"]["veto"] for q in qs)
    assert qs == sorted(qs, key=lambda q: -q["gain"])


def test_action_value(conn):
    data = model.load(conn, DEAL)
    base = model.posterior(data, "2026-10-29")
    one = decision.action_value(data, base, {"sophie_lenoir": "support"}, "2026-10-29")
    two = decision.action_value(data, base, {"sophie_lenoir": "support", "thomas_riou": "support"},
                                "2026-10-29")
    assert 0 < one["gain"] < two["gain"]
