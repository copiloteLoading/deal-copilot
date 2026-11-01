"""Retour d'expérience en fin de contrat, rédigé par Muse Spark à partir de tout le dossier.

Le commercial donne l'issue (signé, perdu, retardé) et, s'il le veut, une phrase sur ce qui a fait
la différence. Muse Spark rend : un résumé, les tournants datés, ce qui a marché, ce qui a bloqué,
et des leçons réutilisables sur d'autres contrats (sans nom de personne ni d'entreprise).
Chaque tournant et chaque leçon s'appuie sur une citation exacte du dossier : celles qu'on ne
retrouve pas mot pour mot sont retirées, comme pour les signaux.
"""

from __future__ import annotations

from copilot import llm
from copilot.extract import _squash
from copilot.forecast import deal_context

OUTCOMES = ["signed", "lost", "delayed"]

SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "turning_points": {"type": "array", "items": {
            "type": "object",
            "properties": {"date": {"type": "string"}, "what": {"type": "string"},
                           "evidence_quote": {"type": "string"}},
            "required": ["date", "what", "evidence_quote"], "additionalProperties": False}},
        "went_well": {"type": "array", "items": {"type": "string"}},
        "went_badly": {"type": "array", "items": {"type": "string"}},
        "lessons": {"type": "array", "items": {
            "type": "object",
            "properties": {"lesson": {"type": "string"}, "applies_when": {"type": "string"},
                           "evidence_quote": {"type": "string"}},
            "required": ["lesson", "applies_when", "evidence_quote"], "additionalProperties": False}},
    },
    "required": ["summary", "turning_points", "went_well", "went_badly", "lessons"],
    "additionalProperties": False,
}

RULES = """You write the end-of-deal review of a large, multi-year infrastructure contract, for the
sales rep who ran it. You get the deal's actors, every debrief in order, and the outcome.

- turning_points: the 2 to 5 moments that changed the course of the deal, each with its date and an
  exact quote copied word for word from the debriefs (a few words are enough).
- went_well / went_badly: decisions and moves by the rep or the selling team, in one sentence each.
- lessons: 2 to 4 lessons the rep can reuse on OTHER deals. Write them in general terms, by role and
  situation ("a finance veto holder who ties approval to the budget cycle"), never with the names of
  people, companies or places from this deal. applies_when: the warning sign that makes the lesson
  relevant on a new deal. evidence_quote: an exact quote from the debriefs that supports it.
- Do not claim causes you cannot prove: say what happened and in what order ("after X, Y followed"),
  not "X caused Y". Plain, grammatical sentences. Never invent numbers. Write in English.
"""


def review(deal: dict, texts: list[tuple[str, str]], outcome: str, rep_note: str = "") -> dict:
    """Retour d'expérience vérifié. outcome : signed / lost / delayed ; rep_note : la phrase du commercial."""
    user = deal_context(deal, texts) + f"\n\nOutcome: {outcome.upper()}"
    if rep_note:
        user += f"\nThe rep's own view of what made the difference: {rep_note}"
    data = llm.chat_json([{"role": "developer", "content": RULES}, {"role": "user", "content": user}],
                         name="review", schema=SCHEMA, **llm.effort("low"))
    source = _squash("\n".join(t for _, t in texts))

    def found(item: dict) -> bool:
        quote = _squash(item.get("evidence_quote", "")).strip("\"' ")
        return len(quote.split()) >= 2 and quote in source

    data["turning_points"] = [t for t in data["turning_points"] if found(t)]
    data["lessons"] = [dict(x, outcome=outcome) for x in data["lessons"] if found(x)]
    return data


def lessons_text(lessons: list[dict]) -> str:
    """Les leçons telles qu'on les donne à Muse Spark sur un nouveau contrat."""
    return "\n".join(f"- [{x['outcome']}] {x['lesson']} (relevant when: {x['applies_when']})" for x in lessons)
