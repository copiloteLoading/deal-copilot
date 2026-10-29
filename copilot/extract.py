"""Extraction des signaux d'un débrief avec Muse Spark (sortie structurée par JSON schema).

Ce que ce module garantit, quoi que réponde le modèle :
- chaque citation est vérifiée mot pour mot dans le débrief ; sinon le signal est écarté ;
- la confiance est bornée entre 0 et 1 ;
- les noms connus du dossier sont fournis au modèle pour qu'il les écrive à l'identique.

Usage : .\\.venv\\Scripts\\python.exe -m copilot.extract samples/debrief_exemple.txt
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from copilot import llm, memory

SIGNAL_TYPES = ["support", "objection", "condition", "commitment", "risk",
                "deadline", "competitor", "budget", "information"]
STANCES = ["support", "conditional", "neutral", "oppose", "unknown"]

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "signals": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "actor_name": {"type": "string"},
                    "entity_kind": {"type": "string", "enum": ["person", "organization"]},
                    "organization": {"type": "string"},
                    "role": {"type": "string"},
                    "signal_type": {"type": "string", "enum": SIGNAL_TYPES},
                    "stance": {"type": "string", "enum": STANCES},
                    "strength": {"type": "string", "enum": ["strong", "weak"]},
                    "source_type": {"type": "string", "enum": ["direct", "reported", "impression"]},
                    "description": {"type": "string"},
                    "evidence_quote": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["actor_name", "entity_kind", "organization", "role", "signal_type",
                             "stance", "strength", "source_type", "description",
                             "evidence_quote", "confidence"],
                "additionalProperties": False,
            },
        },
        "next_steps": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["summary", "signals", "next_steps", "open_questions"],
    "additionalProperties": False,
}

RULES = """You extract deal signals from a sales rep's spoken debrief about a large, multi-year
infrastructure contract. Report only what the debrief says: never invent a person, a number or a stance.

For each signal:
- actor_name: the person concerned. If a known name from the deal context matches, write it exactly
  as in the context. If the signal is about a company, bank or agency and no person is named,
  use the organization name and set entity_kind to "organization".
- stance: the actor's position towards OUR offer.
  "support" = clearly in favour. "oppose" = clearly against or favouring a competitor.
  "conditional" = will agree only if a condition is met, or postpones the decision
  (e.g. "we'll talk about it after the budget"). "neutral" = no preference shown.
  "unknown" = the debrief gives no information on their position.
- strength: "strong" for an explicit, unambiguous statement; "weak" for a hint, a vague remark,
  a nod, or something the rep interprets.
- source_type: "direct" if the actor said or did it in front of the rep; "reported" if someone else
  reported it or the actor was absent; "impression" if it is only the rep's feeling.
- evidence_quote: copy a short passage WORD FOR WORD from the debrief (no paraphrase, no ellipsis).
- confidence (0 to 1): lower it when the rep hesitates ("je crois", "peut-être", "apparemment").
- A deadline or a date is its own signal with signal_type "deadline" and stance "unknown"
  (a date says nothing about anyone's position). Attribute it to the client-side person or
  organization it concerns.
- Our own company (the seller) and its staff are never actors: do not create signals about them.
- An actor who is absent or silent is a "risk" signal with source_type "reported".

Keep the language of the debrief for summary, description, next_steps and open_questions."""


def _deal_context(conn, deal_id: str) -> str:
    """Noms connus du dossier (sans aucune position : le modèle ne doit pas être influencé)."""
    deal = memory.get_deal(conn, deal_id)
    orgs = {o["id"]: o["name"] for o in deal["organizations"]}
    lines = [f"Deal: {deal['name']} (buyer: {deal['buyer']}, our company: {deal['seller']})",
             "Known people:"]
    for a in deal["actors"]:
        lines.append(f"- {a['name']}, {a['role']}, {orgs.get(a['org_id'], '')}"
                     f" (also called: {', '.join(a['aliases'])})")
    lines.append("Known organizations: " + ", ".join(orgs.values()))
    return "\n".join(lines)


def _squash(text: str) -> str:
    """Normalise espaces et apostrophes pour comparer une citation au débrief."""
    text = text.replace("’", "'").replace("«", '"').replace("»", '"')
    return re.sub(r"\s+", " ", text).strip().lower()


def check_signals(text: str, signals: list[dict]) -> tuple[list[dict], list[dict]]:
    """Sépare les signaux dont la citation est bien dans le débrief de ceux qui sont rejetés."""
    source = _squash(text)
    kept, rejected = [], []
    for s in signals:
        quote = _squash(s.get("evidence_quote", "")).strip("\"' ")
        if quote and quote in source:
            s["confidence"] = min(1.0, max(0.0, float(s.get("confidence", 0.5))))
            kept.append(s)
        else:
            rejected.append(s)
    return kept, rejected


def extract(text: str, conn=None, deal_id: str | None = None) -> dict:
    """Extrait les signaux d'un débrief. Le contexte du dossier est ajouté si conn et deal_id sont fournis."""
    user = f"Debrief:\n{text}"
    if conn is not None and deal_id:
        user = f"Deal context:\n{_deal_context(conn, deal_id)}\n\n{user}"
    data = llm.chat_json(
        [{"role": "developer", "content": RULES}, {"role": "user", "content": user}],
        name="deal_signals", schema=SCHEMA, **llm.effort("low"))
    data["signals"], data["rejected"] = check_signals(text, data["signals"])
    return data


def extract_and_store(conn, deal_id: str, date: str, text: str, title: str | None = None) -> dict:
    """Extrait, enregistre la réunion et ses signaux dans la mémoire, et renvoie le tout."""
    data = extract(text, conn, deal_id)
    meeting_id = memory.add_meeting(conn, deal_id, date, title, text, data["summary"])
    data["meeting_id"] = meeting_id
    data["unresolved"] = memory.add_signals(conn, deal_id, meeting_id, data["signals"])
    return data


if __name__ == "__main__":
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "samples/debrief_exemple.txt")
    conn = memory.connect(":memory:")
    deal_id = memory.import_deal(conn, Path("data/demo_deal"))
    result = extract(path.read_text(encoding="utf-8"), conn, deal_id)
    print(result["summary"], "\n")
    for s in result["signals"]:
        print(f"- {s['actor_name']:<34} {s['signal_type']:<11} {s['stance']:<11} "
              f"{s['strength']:<6} {s['source_type']:<10} {s['confidence']:.2f}  « {s['evidence_quote']} »")
    for s in result["rejected"]:
        print(f"! citation introuvable, signal écarté : {s['actor_name']} « {s['evidence_quote']} »")
