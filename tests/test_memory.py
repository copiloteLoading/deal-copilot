"""Tests de la mémoire SQLite (base en mémoire, aucun appel réseau).

Lancer : .\\.venv\\Scripts\\python.exe -m pytest tests -q
"""

from pathlib import Path

import pytest

from copilot import memory

DEMO = Path(__file__).resolve().parent.parent / "data" / "demo_deal"

# Signaux tels que Muse Spark les a extraits du débrief du 27 octobre (test du 29/10),
# complétés du champ source_type que extract.py demandera
EXTRACTED = [
    {"actor_name": "Julien Marec", "organization": "Baltis Telecom", "signal_type": "support",
     "stance": "support", "description": "soutient nos répéteurs",
     "evidence_quote": "la plus solide techniquement", "confidence": 0.95, "source_type": "direct"},
    {"actor_name": "Sophie Lenoir", "organization": "", "signal_type": "objection",
     "stance": "oppose", "description": "veut un phasage sur quatre ans",
     "evidence_quote": "elle veut étaler sur quatre ans au lieu de trois, sinon elle ne valide pas",
     "confidence": 0.9, "source_type": "direct"},
    {"actor_name": "Banque Atlantique de Développement", "organization": "Banque Atlantique de Développement",
     "signal_type": "commitment", "stance": "unknown", "description": "attend l'étude d'impact",
     "evidence_quote": "attend toujours l'étude d'impact environnemental avant de s'engager",
     "confidence": 0.9},
    {"actor_name": "Thomas Riou", "organization": "", "signal_type": "risk", "stance": "unknown",
     "description": "absent depuis six semaines",
     "evidence_quote": "ça fait maintenant six semaines qu'on ne l'a pas vu", "confidence": 0.85,
     "source_type": "reported"},
    {"actor_name": "Oceanix Cables", "organization": "Oceanix Cables", "signal_type": "competitor",
     "stance": "oppose", "description": "prix plus bas, montant incertain",
     "evidence_quote": "ils ont proposé un prix plus bas", "confidence": 0.4},
]


@pytest.fixture
def conn():
    c = memory.connect(":memory:")
    memory.import_deal(c, DEMO)
    return c


def test_import(conn):
    deal = memory.get_deal(conn, "port-aven-kerlis")
    assert len(deal["actors"]) == 6
    vetoes = {a["id"] for a in deal["actors"] if a["veto"]}
    assert vetoes == {"sophie_lenoir", "thomas_riou", "marion_kervella"}
    assert len(memory.meetings(conn, "port-aven-kerlis")) == 3


def test_import_twice_does_not_duplicate(conn):
    memory.import_deal(conn, DEMO)
    assert len(memory.meetings(conn, "port-aven-kerlis")) == 3


@pytest.mark.parametrize("name, expected", [
    ("Sophie Lenoir", ("sophie_lenoir", "baltis")),
    ("la DAF de Baltis", ("sophie_lenoir", "baltis")),
    ("sophie LENOIR", ("sophie_lenoir", "baltis")),
    ("la présidente", ("claire_dantec", "nordlink")),
    ("la presidente", ("claire_dantec", "nordlink")),       # sans accent
    ("Banque Atlantique de Développement", (None, "bad")),  # une organisation, pas une personne
    ("Pierre Inconnu", (None, None)),
])
def test_resolve(conn, name, expected):
    assert memory.resolve(conn, "port-aven-kerlis", name) == expected


def test_keywords(conn):
    words = memory.keywords(conn, "port-aven-kerlis")
    for w in ["Sophie Lenoir", "Thomas Riou", "Baltis Telecom", "Oceanix Cables", "Kervella"]:
        assert w in words
    assert "la banque" not in words           # pas un nom propre
    assert len(words) == len(set(words))      # pas de doublon


def test_add_signals_and_history(conn):
    mid = memory.add_meeting(conn, "port-aven-kerlis", "2026-10-28", "Test")
    unresolved = memory.add_signals(conn, "port-aven-kerlis", mid, EXTRACTED)
    assert unresolved == []                   # tout est rattaché à un acteur ou une organisation

    sophie = memory.signals(conn, "port-aven-kerlis", "sophie_lenoir")
    assert len(sophie) == 1 and sophie[0]["org_id"] == "baltis"
    contact = memory.last_contact(conn, "port-aven-kerlis")
    assert contact["sophie_lenoir"] == "2026-10-28"
    assert contact["thomas_riou"] is None     # cité en son absence : ce n'est pas un contact
    assert contact["marion_kervella"] is None


def test_unresolved_then_alias_confirmed(conn):
    mid = memory.add_meeting(conn, "port-aven-kerlis", "2026-10-28")
    signal = {"actor_name": "le banquier", "organization": "", "signal_type": "risk",
              "stance": "unknown", "evidence_quote": "le banquier ne répond pas", "confidence": 0.7}
    assert memory.add_signals(conn, "port-aven-kerlis", mid, [signal]) == [signal]

    memory.link_alias(conn, "port-aven-kerlis", "thomas_riou", "le banquier")
    riou = memory.signals(conn, "port-aven-kerlis", "thomas_riou")
    assert len(riou) == 1 and riou[0]["confirmed"] == 1
    assert memory.resolve(conn, "port-aven-kerlis", "Le Banquier") == ("thomas_riou", "bad")
