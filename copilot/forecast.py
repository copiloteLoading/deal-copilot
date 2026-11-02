"""Probabilité de signature, estimée par Muse Spark à partir de tout le dossier.

Pourquoi Muse Spark et pas notre modèle par acteur : sur 2 × 10 contrats de test, il prévoit mieux
l'issue (Brier 0,178 contre 0,24 : eval/results.md, eval/results_holdout.md). Sa faiblesse est
l'instabilité d'un tirage à l'autre (jusqu'à 20 points : eval/consistency*.md) ; la moyenne de
N_DRAWS tirages la divise par deux sans perdre en précision (Brier 0,154 contre 0,150 sur 40 points).

Le modèle par acteur garde ce qu'il fait mieux que le LLM : la mémoire de chaque acteur (veto,
silences), le choix des questions et des simulations stables pour classer les actions.
Le texte des consignes est celui de l'évaluation : les mesures restent valables.
"""

from __future__ import annotations

import re
from concurrent.futures import ThreadPoolExecutor

from copilot import llm, memory

N_DRAWS = 3

SCHEMA = {
    "type": "object",
    "properties": {"probability": {"type": "number"}, "rationale": {"type": "string"}},
    "required": ["probability", "rationale"], "additionalProperties": False,
}

RULES = ("You are an experienced sales director. Estimate the probability (between 0 and 1) "
         "that this contract will be SIGNED, as opposed to lost or delayed for a long time. "
         "Veto holders must all agree for the contract to be signed. Be calibrated.")

# poids d'influence recopiés dans l'explication (« Thomas Riou (veto, 0.90) ») : sans intérêt pour le
# commercial. On les retire à l'affichage plutôt que dans la consigne, qui reste celle qui a été mesurée.
WEIGHT = re.compile(r"\s*\((?:veto,\s*)?(?:influence\s*)?[01]?\.\d+\)", re.IGNORECASE)


def deal_context(deal: dict, texts: list[tuple[str, str]]) -> str:
    """Les acteurs du dossier puis tous les comptes rendus (débriefs, réponses, notes), du plus ancien au plus récent."""
    orgs = {o["id"]: o["name"] for o in deal["organizations"]}
    lines = [f"Deal: {deal['name']} · seller: {deal['seller']} · buyer: {deal['buyer']}",
             "Key actors (id | name | role | organization | veto | influence):"]
    lines += [f"- {a['id']} | {a['name']} | {a['role']} | {orgs.get(a['org_id'], '')} | "
              f"{'VETO' if a['veto'] else '-'} | {a['influence']:.2f}" for a in deal["actors"]]
    lines.append("\nDebriefs dictated by the sales rep, oldest first:")
    lines += [f"\n[{day}]\n{text}" for day, text in texts]
    return "\n".join(lines)


def one_draw(deal: dict, texts: list[tuple[str, str]], hypothesis: str | None = None,
             cache_tag: str | None = None, lessons: str | None = None) -> dict:
    """Un tirage : {"probability", "rationale"}. hypothesis : phrase « et si ? » (test de cohérence) ;
    lessons : leçons des contrats passés du commercial (copilot/retro.py)."""
    user = deal_context(deal, texts)
    if lessons:
        user += ("\n\nLessons from the rep's past deals (other contracts, validated by the rep; "
                 "use them only where they fit):\n" + lessons)
    if hypothesis:
        user += f"\n\nHypothesis (assume it is true): {hypothesis}"
    data = llm.chat_json([{"role": "developer", "content": RULES}, {"role": "user", "content": user}],
                         name="forecast", schema=SCHEMA, cache_tag=cache_tag, **llm.effort("low"))
    return {"probability": min(1.0, max(0.0, float(data["probability"]))), "rationale": data["rationale"]}


def forecast(deal: dict, texts: list[tuple[str, str]], lessons: str | None = None) -> dict:
    """Moyenne de N_DRAWS tirages indépendants (lancés en parallèle). Le premier fournit l'explication.
    lessons : leçons des contrats passés (eval/lessons_forecast.md : Brier 0,182 -> 0,163)."""
    tags = [None] + [f"draw{i}" for i in range(1, N_DRAWS)]
    with ThreadPoolExecutor(max_workers=N_DRAWS) as pool:
        draws = list(pool.map(lambda tag: one_draw(deal, texts, cache_tag=tag, lessons=lessons), tags))
    probs = [d["probability"] for d in draws]
    return {"p": sum(probs) / len(probs), "draws": probs, "rationale": WEIGHT.sub("", draws[0]["rationale"])}


def texts_until(conn, deal_id: str, last_meeting_id: int | None = None) -> list[tuple[str, str]]:
    """Ce que le commercial a enregistré (débriefs, réponses aux questions, notes en photo), dans l'ordre
    chronologique, jusqu'à cette réunion incluse. Des notes prises en photo après coup gardent leur date."""
    out = []
    for m in memory.meetings(conn, deal_id):          # triées par date puis par ordre d'ajout
        if m["transcript"]:
            out.append((m["date"], m["transcript"]))
        if m["id"] == last_meeting_id:
            break
    return out
