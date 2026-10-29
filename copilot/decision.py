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

from copilot import model

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
        return (f"À propos de {actor['name']} ({actor['role']}), le débrief dit : « {cond['quote']} ». "
                f"Savez-vous de quoi dépend sa décision, et quand elle sera prise ?", cond)
    if silence is None or silence > SILENCE_DAYS:
        since = f"depuis {silence} jours" if silence is not None else "à ce jour"
        return (f"Aucun échange direct avec {actor['name']} ({actor['role']}) {since}. "
                f"Avez-vous eu un signe, même indirect, de sa position ?", _last(signals))
    return (f"Quelle est aujourd'hui la position de {actor['name']} ({actor['role']}) "
            f"sur notre offre ?", _last(signals))


def rank_questions(data: model.DealData, last_contact: dict[str, str | None],
                   as_of: str | None = None, k: int = 2, min_gain: float = 0.01) -> list[dict]:
    as_of = as_of or date.today().isoformat()
    base = model.posterior(data, as_of)
    out = []
    for a in data.actors:
        b = base.beliefs[a["id"]]
        exp_std = exp_low = exp_high = 0.0
        for i, state in enumerate(model.STATES):
            if b[i] < 1e-3:
                continue
            post = model.simulate(data, {a["id"]: state}, as_of)
            exp_std += b[i] * post.std
            exp_low += b[i] * post.low
            exp_high += b[i] * post.high
        gain = base.std - exp_std
        silence = _days_since(last_contact.get(a["id"]), as_of)
        text, source = _question_text(a, data.signals[a["id"]], silence)
        out.append({"actor": a, "gain": gain, "text": text, "source": source,
                    "expected_low": exp_low, "expected_high": exp_high})
    out.sort(key=lambda q: -q["gain"])
    return [q for q in out if q["gain"] >= min_gain][:k]


def rank_actions(data: model.DealData, last_contact: dict[str, str | None],
                 as_of: str | None = None, k: int = 4) -> list[dict]:
    as_of = as_of or date.today().isoformat()
    base = model.posterior(data, as_of)
    out = []
    for a in data.actors:
        b = base.beliefs[a["id"]]
        if b[0] > 0.85:                       # déjà acquis : rien à gagner
            continue
        after = model.simulate(data, {a["id"]: "support"}, as_of)
        silence = _days_since(last_contact.get(a["id"]), as_of)
        cond = _last(data.signals[a["id"]], stance="conditional")
        if cond:
            title = f"Lever la condition posée par {a['name']}"
            why = f"« {cond['quote']} »"
        elif silence is None or silence > SILENCE_DAYS:
            title = f"Obtenir un rendez-vous avec {a['name']} ({a['role']})"
            why = "jamais rencontré(e) directement" if silence is None else f"aucun échange direct depuis {silence} jours"
        else:
            title = f"Consolider le soutien de {a['name']} ({a['role']})"
            why = f"position actuelle incertaine ({b[0]:.0%} favorable)"
        if a["veto"]:
            why = "détenteur de veto · " + why
        out.append({"actor": a, "title": title, "why": why, "source": cond or _last(data.signals[a["id"]]),
                    "p_before": base.p, "p_after": after.p, "gain": after.p - base.p})
    out.sort(key=lambda x: -x["gain"])
    return out[:k]
