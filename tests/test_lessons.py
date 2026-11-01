"""Leçons des contrats passés : chargement, clôture d'un contrat, citation par l'agent (aucun appel réseau)."""

from copilot import agent, memory, model, pipeline

LESSON = {"lesson": "lift budget conditions before the vote", "applies_when": "a finance veto mentions the budget",
          "evidence_quote": "after the budget"}


def demo():
    conn = memory.connect(":memory:")
    memory.import_deal(conn, pipeline.DEMO_DIR)      # sans extraction (pas de réseau)
    return conn, pipeline.DEMO_ID


def test_past_lessons_are_loaded_once(monkeypatch):
    conn, d = demo()
    monkeypatch.setattr(pipeline.extract, "extract", lambda *a, **k: {"signals": [], "summary": ""})
    pipeline.setup_demo(conn)
    n = len(memory.lessons(conn, exclude_deal=d))
    assert n >= 30                                   # data/past_lessons.json
    pipeline.setup_demo(conn, reset=True)
    assert len(memory.lessons(conn, exclude_deal=d)) == n


def test_closing_keeps_lessons_and_reopening_removes_them():
    conn, d = demo()
    memory.add_lessons(conn, "other-deal", "Other", "signed", [LESSON])
    pipeline.close_deal(conn, d, "lost", [LESSON], day="2026-11-01")
    assert memory.closure(conn, d) == {"deal_id": d, "outcome": "lost", "closed_on": "2026-11-01"}
    assert len(memory.lessons(conn)) == 2
    assert [x["source_deal"] for x in memory.lessons(conn, exclude_deal=d)] == ["other-deal"]   # pas les siennes
    memory.import_deal(conn, pipeline.DEMO_DIR)      # contrat rouvert depuis le début
    assert memory.closure(conn, d) is None
    assert [x["source_deal"] for x in memory.lessons(conn)] == ["other-deal"]


def test_agent_keeps_only_real_lesson_ids():
    conn, d = demo()
    memory.add_lessons(conn, "other-deal", "Other", "lost", [LESSON])
    past = memory.lessons(conn, exclude_deal=d)
    data = model.load(conn, d)
    veto = next(a for a in data.actors if a["veto"])
    plan = {"questions": [], "actions": [{"title": "Lift the condition", "rationale": "budget condition",
                                          "effects": [{"actor_id": veto["id"], "stance": "support"}],
                                          "signal_ids": [], "lesson_ids": [past[0]["id"], 999]}]}
    out = agent.finalize(data, plan, "2026-10-29", past)
    assert [x["lesson"] for x in out["actions"][0]["lessons"]] == [LESSON["lesson"]]
