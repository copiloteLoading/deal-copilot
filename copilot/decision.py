"""Moteur de décision : quelle question ou quelle action changerait le plus la probabilité ?

Questions (valeur de l'information) : pour chaque acteur, on imagine chaque réponse possible
(il est pour / neutre / contre), pondérée par sa probabilité actuelle, et on calcule de combien
l'incertitude sur la signature (écart-type des tirages Monte-Carlo) baisserait en moyenne.
On pose les questions qui la réduisent le plus, au plus 2, et on s'arrête quand le gain
devient négligeable. L'écart-type sert au classement car il varie régulièrement ; l'intervalle
à 80 % attendu après la réponse est seulement affiché.

Actions (effet attendu) : pour chaque acteur qui n'est pas déjà acquis, on simule
« il devient favorable » et on mesure le gain de probabilité.

Tous les chiffres viennent du modèle (model.py). Les textes sont des gabarits en attendant
que l'agent (agent.py) les reformule avec Muse Spark.
"""

from __future__ import annotations

from datetime import date

from copilot import clock, model

SILENCE_DAYS = 30


def _last(signals: list[dict], **match) -> dict | None:
    for s in reversed(signals):
        if all(s.get(k) == v for k, v in match.items()):
            return s
    return None


def _days_since(day: str | None, today: str) -> int | None:
    return None if day is None else (date.fromisoformat(today) - date.fromisoformat(day)).days


def _question_text(actor: dict, signals: list[dict], silence: int | None) -> tuple[str, dict | None]:
    """Gabarit de question, avec le signal qui la justifie (pour la citation)."""
    cond = _last(signals, stance="conditional")
    if cond:
        return (f"About {actor['name']} ({actor['role']}), the debrief says: \u201c{cond['quote']}\u201d. "
                f"Do you know what their decision depends on, and when it will be taken?", cond)
    if silence is None or silence > SILENCE_DAYS:
        since = f"for {silence} days" if silence is not None else "so far"
        return (f"No direct exchange with {actor['name']} ({actor['role']}) {since}. "
                f"Have you had any sign, even indirect, of their position?", _last(signals))
    return (f"Where does {actor['name']} ({actor['role']}) stand on our offer today?", _last(signals))


def question_value(data: model.DealData, base: model.Posterior, actor_id: str,
                   as_of: str) -> dict:
    """Valeur de l'information d'une question sur un acteur : baisse attendue de l'écart-type,
    en moyenne sur ses positions possibles pondérées par leur probabilité actuelle."""
    b = base.beliefs[actor_id]
    exp_std = exp_low = exp_high = 0.0
    for i, state in enumerate(model.STATES):
        if b[i] < 1e-3:
            continue
        post = model.simulate(data, {actor_id: state}, as_of)
        exp_std += b[i] * post.std
        exp_low += b[i] * post.low
        exp_high += b[i] * post.high
    return {"gain": base.std - exp_std, "expected_low": exp_low, "expected_high": exp_high}


def action_value(data: model.DealData, base: model.Posterior, effects: dict[str, str],
                 as_of: str) -> dict:
    """Probabilité si l'action réussit, c'est-à-dire si les acteurs visés prennent ces positions."""
    after = model.simulate(data, effects, as_of)
    return {"p_before": base.p, "p_after": after.p, "gain": after.p - base.p}


def rank_questions(data: model.DealData, last_contact: dict[str, str | None],
                   as_of: str | None = None, k: int = 2, min_gain: float = 0.01) -> list[dict]:
    as_of = as_of or clock.today().isoformat()
    base = model.posterior(data, as_of)
    out = []
    for a in data.actors:
        silence = _days_since(last_contact.get(a["id"]), as_of)
        text, source = _question_text(a, data.signals[a["id"]], silence)
        out.append({"actor": a, "text": text, "source": source,
                    **question_value(data, base, a["id"], as_of)})
    out.sort(key=lambda q: -q["gain"])
    return [q for q in out if q["gain"] >= min_gain][:k]


def rank_actions(data: model.DealData, last_contact: dict[str, str | None],
                 as_of: str | None = None, k: int = 4) -> list[dict]:
    as_of = as_of or clock.today().isoformat()
    base = model.posterior(data, as_of)
    out = []
    for a in data.actors:
        b = base.beliefs[a["id"]]
        if b[0] > 0.85:                       # déjà acquis : rien à gagner
            continue
        silence = _days_since(last_contact.get(a["id"]), as_of)
        cond = _last(data.signals[a["id"]], stance="conditional")
        if cond:
            title = f"Lift the condition set by {a['name']}"
            why = f"\u201c{cond['quote']}\u201d"
        elif silence is None or silence > SILENCE_DAYS:
            title = f"Get a meeting with {a['name']} ({a['role']})"
            why = "never met directly" if silence is None else f"no direct exchange for {silence} days"
        else:
            title = f"Secure {a['name']}'s support ({a['role']})"
            why = "current position uncertain"
        if a["veto"]:
            why = "veto holder · " + why
        out.append({"actor": a, "title": title, "why": why, "source": cond or _last(data.signals[a["id"]]),
                    "effects": {a["id"]: "support"},
                    **action_value(data, base, {a["id"]: "support"}, as_of)})
    out.sort(key=lambda x: -x["gain"])
    return out[:k]
