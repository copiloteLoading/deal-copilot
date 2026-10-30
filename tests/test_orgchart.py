"""Tests de la lecture d'organigramme avec un faux Muse Spark (aucun appel réseau)."""

from pathlib import Path

import pytest

from copilot import llm, memory, model, orgchart, photo

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo_deal"
DEAL = "port-aven-kerlis"

CHART = {
    "organizations": [{"name": "Baltis Telecom", "type": "consortium_member"},
                      {"name": "Cabinet Ternaud", "type": "subcontractor"}],
    "people": [
        {"name": "Hervé Quillec", "role": "Directeur général", "organization": "Baltis Telecom",
         "manager": "", "level": 1},
        {"name": "Sophie Lenoir", "role": "Directrice financière", "organization": "Baltis Telecom",
         "manager": "Hervé Quillec", "level": 2},
        {"name": "Paul Ternaud", "role": "Conseil juridique", "organization": "Cabinet Ternaud",
         "manager": "", "level": 3},
    ],
}


@pytest.fixture
def conn():
    c = memory.connect(":memory:")
    memory.import_deal(c, DEMO)
    return c


def test_read_sends_the_image_in_the_user_message(monkeypatch):
    seen = {}

    def fake(messages, **k):
        seen["messages"] = messages
        return CHART

    monkeypatch.setattr(llm, "chat_json", fake)
    assert photo.read(b"\xff\xd8fake", "image/jpeg", "Port-Lazen", ["Sophie Lenoir"]) == CHART
    user = seen["messages"][1]
    assert user["role"] == "user" and user["content"][1]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "Sophie Lenoir" in user["content"][0]["text"]          # noms connus : aide à la lecture


def test_propose_matches_known_people_and_orgs(conn):
    rows = {r["name"]: r for r in orgchart.propose(conn, DEAL, CHART)}
    assert rows["Sophie Lenoir"]["known_as"] == "sophie_lenoir" and not rows["Sophie Lenoir"]["add"]
    assert rows["Hervé Quillec"]["org_id"] == "baltis" and rows["Hervé Quillec"]["influence"] == 0.8
    assert rows["Paul Ternaud"]["org_id"] is None and not rows["Paul Ternaud"]["veto"]


def test_apply_adds_new_people_without_overwriting(conn):
    rows = orgchart.propose(conn, DEAL, CHART)
    created = orgchart.apply(conn, DEAL, rows)
    assert created == ["herve_quillec", "paul_ternaud"]
    deal = memory.get_deal(conn, DEAL)
    assert any(o["name"] == "Cabinet Ternaud" for o in deal["organizations"])
    assert next(a for a in deal["actors"] if a["id"] == "sophie_lenoir")["veto"]      # intact
    assert memory.resolve(conn, DEAL, "Quillec")[0] == "herve_quillec"                # alias
    data = model.load(conn, DEAL)
    assert "herve_quillec" in model.posterior(data, "2026-10-29").beliefs           # le modèle le voit


def test_reporting_line_is_recorded(conn):
    orgchart.apply(conn, DEAL, orgchart.propose(conn, DEAL, CHART))
    deal = memory.get_deal(conn, DEAL)
    assert next(a for a in deal["actors"] if a["id"] == "sophie_lenoir")["manager_id"] == "herve_quillec"


def test_set_manager_refuses_loops(conn):
    memory.set_manager(conn, DEAL, "julien_marec", "sophie_lenoir")
    with pytest.raises(ValueError):
        memory.set_manager(conn, DEAL, "sophie_lenoir", "julien_marec")
