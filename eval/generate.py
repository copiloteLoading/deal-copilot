"""Génère le jeu de test : des contrats fictifs, leur vérité cachée et les débriefs du commercial.

Muse Spark écrit tout, SANS connaître la structure de notre modèle :
1. une fiche par contrat : entreprises, personnages avec intérêts cachés, veto, position réelle
   de chaque acteur à chaque réunion, et l'issue finale (signé, perdu, retardé) ;
2. pour chaque réunion, le débrief dicté par un commercial qui perçoit mal (oublis, hésitations,
   optimisme, absents), plus la liste de ce que ce débrief exprime vraiment (pour noter l'extraction).

Sortie : data/scenarios/<id>/deal.json (format de memory.import_deal), debriefs/*.txt,
truth.json (vérité cachée, jamais donnée au modèle) et gold.json (ce que disent les débriefs).

Usage : .\\.venv\\Scripts\\python.exe -m eval.generate [nombre]     (2 pour un premier essai)
Jeux : dev (défaut, data/scenarios/) ou holdout (data/scenarios_holdout/), en premier argument.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from copilot import llm

OUT = Path(__file__).resolve().parent.parent / "data" / "scenarios"
STANCES = ["support", "neutral", "oppose"]

# Diversité imposée : secteur, issue, et ressort principal de l'histoire
SPECS = [
    ("submarine telecom cable", "signed", "a skeptical finance director is won over by a payment schedule"),
    ("offshore wind farm export cable", "lost", "the lender silently walks away after a delayed environmental study"),
    ("hyperscale data center power and cooling", "signed", "a strong technical champion carries a cautious buyer"),
    ("submarine power interconnector between two private grids", "lost", "a competitor undercuts the price and the procurement head switches"),
    ("offshore wind substation", "delayed", "the regulator's permit takes much longer than planned"),
    ("regional fiber backbone for a telecom operator", "signed", "an early opponent changes their mind after a site visit"),
    ("data center campus with on-site energy storage", "lost", "the CFO never budgets the project despite friendly meetings"),
    ("submarine cable repair and maintenance framework", "signed", "steady support but a slow legal review"),
    ("floating offshore wind pilot farm", "delayed", "the consortium partners disagree on cost sharing"),
    ("subsea cable for an island grid", "lost", "the board chair favours a local supplier from the start"),
]

# Jeu de validation : d'autres intrigues, générées APRÈS les réglages faits sur le premier jeu,
# pour mesurer honnêtement le modèle sur des contrats qu'il n'a jamais vus.
HOLDOUT_SPECS = [
    ("submarine cable landing station upgrade", "signed",
     "procurement demands a price cut, granted against a longer maintenance contract"),
    ("offshore wind array cables", "lost",
     "the technical champion leaves the buyer company and his successor prefers the incumbent supplier"),
    ("edge data centers for a telecom operator", "signed",
     "the lender requires an independent technical audit that turns out positive"),
    ("subsea fiber link for an offshore research station operator", "lost",
     "the CFO keeps postponing and finally freezes all capital spending"),
    ("data center cooling retrofit", "delayed",
     "the grid connection from the private utility company takes months longer than planned"),
    ("inter-island submarine telecom cable", "signed",
     "a lukewarm consortium partner is convinced by a revenue-sharing proposal"),
    ("offshore wind cable repair framework", "lost",
     "the lead lender demands guarantees the seller cannot provide"),
    ("metropolitan fiber ring for a private network operator", "signed",
     "a long legal negotiation on liability caps finally converges"),
    ("hydrogen-ready offshore substation", "delayed",
     "the buyer's board asks for a new feasibility study after a change of strategy"),
    ("hyperscale data center power distribution", "lost",
     "an enthusiastic sponsor is overruled by a procurement committee that picks a cheaper bid"),
]
SETS = {"dev": (SPECS, OUT), "holdout": (HOLDOUT_SPECS, OUT.parent / "scenarios_holdout")}

SHEET_SCHEMA = {
    "type": "object",
    "properties": {
        "deal_name": {"type": "string"},
        "description": {"type": "string"},
        "seller": {"type": "string"},
        "sales_rep": {"type": "string"},
        "buyer": {"type": "string"},
        "value_meur": {"type": "number"},
        "competitors": {"type": "array", "items": {"type": "string"}},
        "organizations": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "name": {"type": "string"},
            "type": {"type": "string", "enum": ["buyer", "consortium_member", "financier",
                                                "regulator", "subcontractor", "competitor"]},
            "aliases": {"type": "array", "items": {"type": "string"}}},
            "required": ["id", "name", "type", "aliases"], "additionalProperties": False}},
        "actors": {"type": "array", "items": {"type": "object", "properties": {
            "id": {"type": "string"}, "name": {"type": "string"}, "org_id": {"type": "string"},
            "role": {"type": "string"}, "influence": {"type": "number"}, "veto": {"type": "boolean"},
            "hidden_interest": {"type": "string"},
            "aliases": {"type": "array", "items": {"type": "string"}}},
            "required": ["id", "name", "org_id", "role", "influence", "veto", "hidden_interest",
                         "aliases"], "additionalProperties": False}},
        "meetings": {"type": "array", "items": {"type": "object", "properties": {
            "date": {"type": "string"}, "title": {"type": "string"},
            "attendees": {"type": "array", "items": {"type": "string"}},
            "what_really_happens": {"type": "string"},
            "true_positions": {"type": "array", "items": {"type": "object", "properties": {
                "actor_id": {"type": "string"}, "stance": {"type": "string", "enum": STANCES}},
                "required": ["actor_id", "stance"], "additionalProperties": False}}},
            "required": ["date", "title", "attendees", "what_really_happens", "true_positions"],
            "additionalProperties": False}},
        "outcome": {"type": "string", "enum": ["signed", "lost", "delayed"]},
        "outcome_explanation": {"type": "string"},
    },
    "required": ["deal_name", "description", "seller", "sales_rep", "buyer", "value_meur",
                 "competitors", "organizations", "actors", "meetings", "outcome",
                 "outcome_explanation"],
    "additionalProperties": False,
}

SHEET_RULES = """You write realistic, entirely FICTIONAL case files for the evaluation of a sales tool.
Each case is a multi-year B2B infrastructure contract negotiated by a seller company with a buyer.
Constraints:
- Everything is invented: companies, people, places. Never use a real company, a real person or a
  real place. Companies and private lenders only: no countries, governments, politics or conflicts.
- 5 to 7 key actors on the buyer side (buyer, consortium members, lender, regulator...), with
  2 or 3 veto holders (people whose refusal blocks signature). influence between 0 and 1.
  Give each actor 1 to 3 aliases a sales rep would use ("la DAF", "Marc", "le banquier").
- 4 meetings between February and October 2026 (ISO dates), ALL BEFORE the final decision: the
  outcome is decided some weeks after the 4th meeting, so no meeting announces it (no signature,
  no award, no official rejection or postponement during the meetings). For each meeting give the
  TRUE stance of EVERY actor at that date (support / neutral / oppose), even if they did not attend.
  Stances may change over time, as in real life, and should already point towards the outcome.
- The outcome must follow from the story. Use the outcome and plot given by the user.
- ids are short snake_case. Organization names, people and the seller are in French style.
- Write description, roles and explanations in French."""

DEBRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "debrief": {"type": "string"},
        "mentions": {"type": "array", "items": {"type": "object", "properties": {
            "actor_id": {"type": "string"},
            "stance_expressed": {"type": "string",
                                 "enum": ["support", "conditional", "neutral", "oppose"]}},
            "required": ["actor_id", "stance_expressed"], "additionalProperties": False}},
    },
    "required": ["debrief", "mentions"],
    "additionalProperties": False,
}

DEBRIEF_RULES = """You play the sales rep of the seller. Right after a meeting you dictate a short spoken
debrief in French (120 to 220 words, natural spoken style, no bullet points).
You only know what you saw and heard in this meeting: you do NOT know the true positions given in
the case file. Like a real rep you are imperfect: you sometimes forget someone, hesitate
("je crois", "apparemment"), are a bit optimistic, report rumours, mention who was absent.
Use the people's names or aliases as a rep would. Do not write any probability.
The final decision has NOT been taken yet: never say the contract is signed, won, lost, awarded
or postponed; you can only report what people said and did in this meeting.
Then list in "mentions" what your debrief actually expresses about each actor's position
(only actors your debrief says something about; "conditional" when they set a condition or postpone)."""


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:40]


def make_sheet(i: int, specs: list = SPECS) -> dict:
    sector, outcome, plot = specs[i]
    user = f"Case {i + 1}. Sector: {sector}. Outcome: {outcome}. Plot: {plot}."
    return llm.chat_json([{"role": "developer", "content": SHEET_RULES},
                          {"role": "user", "content": user}],
                         name="case_file", schema=SHEET_SCHEMA, **llm.effort("medium"))


def make_debrief(sheet: dict, k: int) -> dict:
    """Débrief de la réunion k : le rédacteur voit la fiche jusqu'à cette réunion (pas la suite)."""
    visible = {**sheet, "meetings": sheet["meetings"][:k + 1]}
    visible.pop("outcome", None)
    visible.pop("outcome_explanation", None)
    m = sheet["meetings"][k]
    user = (f"Case file (hidden from the rep, for your information only):\n"
            f"{json.dumps(visible, ensure_ascii=False)}\n\n"
            f"Dictate the debrief of the meeting of {m['date']} ({m['title']}).")
    return llm.chat_json([{"role": "developer", "content": DEBRIEF_RULES},
                          {"role": "user", "content": user}],
                         name="debrief", schema=DEBRIEF_SCHEMA, **llm.effort("low"))


def check(sheet: dict) -> list[str]:
    """Contrôles de cohérence d'une fiche ; renvoie la liste des problèmes."""
    problems = []
    orgs = {o["id"] for o in sheet["organizations"]}
    actors = {a["id"] for a in sheet["actors"]}
    if not 5 <= len(actors) <= 7:
        problems.append(f"{len(actors)} acteurs")
    if not 2 <= sum(a["veto"] for a in sheet["actors"]) <= 3:
        problems.append("nombre de veto")
    problems += [f"org inconnue {a['org_id']}" for a in sheet["actors"] if a["org_id"] not in orgs]
    if len(sheet["meetings"]) != 4:
        problems.append(f"{len(sheet['meetings'])} réunions")
    for m in sheet["meetings"]:
        if {p["actor_id"] for p in m["true_positions"]} != actors:
            problems.append(f"positions incomplètes le {m['date']}")
    return problems


def save(i: int, sheet: dict, debriefs: list[dict], out: Path = OUT) -> Path:
    folder = out / f"{i + 1:02d}_{_slug(sheet['deal_name'])}"
    (folder / "debriefs").mkdir(parents=True, exist_ok=True)
    deal_id = folder.name
    org_names = {o["id"]: o["name"] for o in sheet["organizations"]}
    buyer = org_names.get(sheet["buyer"], sheet["buyer"])      # le modèle donne parfois un id
    meetings = []
    for k, (m, d) in enumerate(zip(sheet["meetings"], debriefs)):
        path = f"debriefs/{k + 1}_{m['date']}.txt"
        (folder / path).write_text(d["debrief"], encoding="utf-8")
        meetings.append({"date": m["date"], "title": m["title"], "debrief": path})
    deal = {"_note": "Contrat fictif généré par Muse Spark pour l'évaluation.",
            "deal_id": deal_id, "name": sheet["deal_name"], "seller": sheet["seller"],
            "sales_rep": sheet["sales_rep"], "buyer": buyer,
            "description": sheet["description"], "value_meur": sheet["value_meur"],
            "opened": sheet["meetings"][0]["date"], "target_signature": None,
            "competitors": sheet["competitors"], "organizations": sheet["organizations"],
            "actors": [{"id": a["id"], "name": a["name"], "org": a["org_id"], "role": a["role"],
                        "influence": a["influence"], "veto": a["veto"], "aliases": a["aliases"]}
                       for a in sheet["actors"]],
            "meetings": meetings}
    truth = {"outcome": sheet["outcome"], "outcome_explanation": sheet["outcome_explanation"],
             "hidden_interests": {a["id"]: a["hidden_interest"] for a in sheet["actors"]},
             "positions": [{"date": m["date"], "attendees": m["attendees"],
                            "what_really_happens": m["what_really_happens"],
                            "stances": {p["actor_id"]: p["stance"] for p in m["true_positions"]}}
                           for m in sheet["meetings"]]}
    gold = [{"date": m["date"], "mentions": d["mentions"]} for m, d in zip(sheet["meetings"], debriefs)]
    for name, obj in [("deal.json", deal), ("truth.json", truth), ("gold.json", gold)]:
        (folder / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return folder


def generate(i: int, name: str = "dev") -> tuple[int, str]:
    specs, out = SETS[name]
    sheet = make_sheet(i, specs)
    problems = check(sheet)
    if problems:
        return i, f"fiche rejetée : {problems}"
    debriefs = [make_debrief(sheet, k) for k in range(len(sheet["meetings"]))]
    folder = save(i, sheet, debriefs, out)
    return i, f"ok -> {folder.name} ({sheet['outcome']})"


if __name__ == "__main__":
    args = sys.argv[1:]
    name = args.pop(0) if args and args[0] in SETS else "dev"
    n = int(args[0]) if args else len(SETS[name][0])
    with ThreadPoolExecutor(max_workers=5) as pool:
        for i, msg in pool.map(lambda i: generate(i, name), range(n)):
            print(f"contrat {i + 1}: {msg}")
