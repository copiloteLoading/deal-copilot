"""Tests du retour d'expérience avec un faux modèle (aucun appel réseau)."""

from copilot import llm, retro

DEAL = {"name": "Test cable", "seller": "S", "buyer": "B", "organizations": [{"id": "o", "name": "Org"}],
        "actors": [{"id": "a", "name": "Ann Roe", "role": "CFO", "org_id": "o", "veto": True, "influence": 0.9}]}
TEXTS = [("2026-01-10", "Ann said we'll talk about it after the budget."),
         ("2026-03-02", "Ann finally approved the phased payment plan.")]


def test_review_keeps_only_verified_quotes(monkeypatch):
    def fake(messages, name, schema, **k):
        assert "Outcome: SIGNED" in messages[1]["content"]
        return {"summary": "s", "went_well": [], "went_badly": [],
                "turning_points": [{"date": "2026-03-02", "what": "approval", "evidence_quote": "approved the phased payment plan"},
                                   {"date": "2026-02-01", "what": "made up", "evidence_quote": "the board loved it"}],
                "lessons": [{"lesson": "tie payments to milestones", "applies_when": "budget cycle",
                             "evidence_quote": "after the budget"},
                            {"lesson": "one word", "applies_when": "x", "evidence_quote": "Ann"}]}

    monkeypatch.setattr(llm, "chat_json", fake)
    out = retro.review(DEAL, TEXTS, "signed", "the phasing did it")
    assert [t["what"] for t in out["turning_points"]] == ["approval"]
    assert [x["lesson"] for x in out["lessons"]] == ["tie payments to milestones"]
    assert out["lessons"][0]["outcome"] == "signed"
    assert retro.lessons_text(out["lessons"]).startswith("- [signed] tie payments")
