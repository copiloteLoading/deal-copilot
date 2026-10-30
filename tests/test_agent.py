"""Tests de l'agent avec un faux Muse Spark : la boucle d'outils et la vérification du plan."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from copilot import agent, llm, memory, model

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo_deal"
DEAL = "port-aven-kerlis"


@pytest.fixture
def conn():
    c = memory.connect(":memory:")
    memory.import_deal(c, DEMO)
    mid = memory.add_meeting(c, DEAL, "2026-10-29", "Débrief")
    memory.add_signals(c, DEAL, mid, [
        {"actor_name": "Sophie Lenoir", "signal_type": "condition", "stance": "conditional",
         "strength": "strong", "source_type": "direct", "evidence_quote": "after the budget",
         "confidence": 0.9}])
    return c


def call(name, args, i=0):
    return SimpleNamespace(id=f"call_{name}_{i}",
                           function=SimpleNamespace(name=name, arguments=json.dumps(args)))


def message(*calls):
    msg = SimpleNamespace(tool_calls=list(calls) or None, content=None)
    msg.model_dump = lambda **k: {"role": "assistant", "content": None}
    return msg


GOOD_PLAN = {
    "questions": [
        {"actor_id": "sophie_lenoir", "text": "Do you know whether the project is in the budget?",
         "signal_ids": [1, 999]},
        {"actor_id": "inconnu", "text": "Question sur personne ?", "signal_ids": []},
        {"actor_id": "thomas_riou", "text": "La banque a-t-elle 80 % de chances de suivre ?",
         "signal_ids": []},
    ],
    "actions": [
        {"title": "Propose a payment schedule", "rationale": "Finance asks for a longer schedule.",
         "effects": [{"actor_id": "sophie_lenoir", "stance": "support"}], "signal_ids": [1]},
        {"title": "Propose a guaranteed schedule", "rationale": "For finance and the bank.",
         "effects": [{"actor_id": "sophie_lenoir", "stance": "support"},
                     {"actor_id": "thomas_riou", "stance": "support"}], "signal_ids": []},
        {"title": "Action sans effet", "rationale": "Rien.", "effects": [], "signal_ids": []},
    ],
}


def test_finalize_checks_and_ranks_with_the_model(conn):
    data = model.load(conn, DEAL)
    out = agent.finalize(data, GOOD_PLAN, "2026-10-29")
    assert [q["actor"]["id"] for q in out["questions"]] == ["sophie_lenoir"]   # inconnu et chiffre écartés
    assert out["questions"][0]["sources"][0]["quote"] == "after the budget"       # id 999 ignoré
    titles = [a["title"] for a in out["actions"]]
    assert titles == ["Propose a guaranteed schedule", "Propose a payment schedule"]  # classé par le modèle
    assert len(out["rejected"]) == 3


def test_tools_report_errors_instead_of_crashing(conn):
    data = model.load(conn, DEAL)
    tools = agent.Tools(data, model.posterior(data, "2026-10-29"), "2026-10-29")
    assert "error" in tools.run("evaluate_question", {"actor_id": "personne"})
    res = tools.run("simulate_action", {"effects": [{"actor_id": "sophie_lenoir", "stance": "support"}]})
    assert res["probability_if_success_percent"] > res["probability_now_percent"]


def test_run_loop_with_fake_model(conn, monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(llm, "provider", lambda: "meta")
    turns = iter([
        message(call("evaluate_question", {"actor_id": "sophie_lenoir"}),
                call("simulate_action", {"effects": [{"actor_id": "sophie_lenoir", "stance": "support"}]})),
        message(call("submit_plan", GOOD_PLAN)),
    ])
    calls = []

    def fake_chat_tools(messages, tools, tool_choice="auto", **params):
        calls.append(tool_choice)
        return next(turns)

    monkeypatch.setattr(llm, "chat_tools", fake_chat_tools)
    out = agent.run(conn, DEAL, "2026-10-29")
    assert out["steps"] == 2 and len(calls) == 2
    assert [c["tool"] for c in out["trace"]] == ["evaluate_question", "simulate_action", "submit_plan"]
    assert out["questions"][0]["actor"]["id"] == "sophie_lenoir"

    # deuxième appel : relu depuis le cache, sans appeler le modèle
    monkeypatch.setattr(llm, "chat_tools", lambda *a, **k: pytest.fail("cache non utilisé"))
    assert agent.run(conn, DEAL, "2026-10-29")["steps"] == 2
