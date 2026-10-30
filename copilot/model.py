"""Modèle stochastique : position cachée de chaque acteur, règle de veto, Monte-Carlo.

Pour chaque acteur, la position cachée est une distribution sur {support, neutral, oppose} :
- elle part d'un a priori (config/model_params.yaml) ;
- chaque signal du débrief la met à jour par la règle de Bayes (vraisemblance tempérée
  par la confiance, la force et l'origine du signal) ;
- entre deux signaux, elle dérive vers l'a priori : le silence se paie.
C'est un filtre forward de modèle de Markov caché, acteur par acteur.

La probabilité de signature exige que chaque détenteur de veto laisse passer, et pondère
les autres acteurs par leur influence. On tire les positions au hasard (Monte-Carlo) pour
obtenir la probabilité moyenne et son intervalle à 80 %.
Hypothèse simplificatrice : les acteurs sont indépendants entre eux.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path

import numpy as np
import yaml

from copilot import clock, memory

# MODEL_PARAMS permet de comparer une autre version des paramètres (évaluation)
PARAMS_PATH = Path(os.environ.get("MODEL_PARAMS")
                   or Path(__file__).resolve().parent.parent / "config" / "model_params.yaml")
STATES = ["support", "neutral", "oppose"]


@lru_cache
def params() -> dict:
    return yaml.safe_load(PARAMS_PATH.read_text(encoding="utf-8"))


def _weeks(start: str, end: str) -> float:
    return max(0.0, (date.fromisoformat(end) - date.fromisoformat(start)).days / 7)


def _drift(p: np.ndarray, prior: np.ndarray, weeks: float) -> np.ndarray:
    """Sans nouvelle, la position revient vers l'a priori."""
    return prior + (p - prior) * (1 - params()["weekly_drift"]) ** weeks


def signal_weight(s: dict) -> float:
    """Poids d'une observation entre 0 et 1 : confiance × force × origine."""
    P = params()
    return (float(s.get("confidence") or 0.5)
            * P["strength_weight"].get(s.get("strength") or "strong", 1.0)
            * P["source_weight"].get(s.get("source_type") or "direct", 1.0))


@dataclass
class DealData:
    """Ce dont le modèle a besoin, lu une seule fois dans la mémoire."""
    deal: dict
    actors: list[dict]
    signals: dict[str, list[dict]]   # signaux utilisables, par acteur, dans l'ordre chronologique
    org_types: dict[str, str]        # acteur -> type de son organisation (regulator, financier...)


def load(conn, deal_id: str) -> DealData:
    deal = memory.get_deal(conn, deal_id)
    actors = deal["actors"]
    by_org: dict[str, list[str]] = {}
    for a in actors:
        by_org.setdefault(a["org_id"], []).append(a["id"])
    usable = {a["id"]: [] for a in actors}
    for s in memory.signals(conn, deal_id):
        if s["signal_type"] == "deadline" or s["stance"] not in params()["likelihood"]:
            continue
        actor_id = s["actor_id"]
        # un signal sur une organisation vaut pour son unique interlocuteur connu (ex. la banque)
        if actor_id is None and len(by_org.get(s["org_id"], [])) == 1:
            actor_id = by_org[s["org_id"]][0]
        if actor_id in usable:
            usable[actor_id].append(s)
    types = {o["id"]: o["type"] for o in deal["organizations"]}
    return DealData(deal, actors, usable, {a["id"]: types.get(a["org_id"]) for a in actors})


def belief(data: DealData, actor_id: str, as_of: str, exclude: set[int] = frozenset()) -> np.ndarray:
    """Distribution de la position d'un acteur à une date (filtre forward)."""
    P = params()
    prior = np.array(P["prior_by_org_type"].get(data.org_types.get(actor_id), P["prior"]), dtype=float)
    p, t = prior.copy(), None
    for s in data.signals[actor_id]:
        if s["date"] > as_of or s["id"] in exclude:
            continue
        if t is not None:
            p = _drift(p, prior, _weeks(t, s["date"]))
        t = s["date"] if t is None else max(t, s["date"])
        p = p * np.array(P["likelihood"][s["stance"]]) ** signal_weight(s)
        p = p / p.sum()
    return p if t is None else _drift(p, prior, _weeks(t, as_of))


@dataclass
class Posterior:
    beliefs: dict[str, np.ndarray]   # acteur -> [p_support, p_neutral, p_oppose]
    p: float                         # probabilité de signature
    low: float                       # bornes de l'intervalle à 80 %
    high: float
    std: float                       # écart-type des tirages : mesure d'incertitude régulière

    @property
    def width(self) -> float:
        return self.high - self.low


def signature_draws(data: DealData, beliefs: dict[str, np.ndarray]) -> np.ndarray:
    """Tire les positions des acteurs et renvoie la probabilité de signature de chaque tirage."""
    P = params()
    rng = np.random.default_rng(P["seed"])
    n = P["n_draws"]
    ids = [a["id"] for a in data.actors]
    B = np.array([beliefs[i] for i in ids])                        # acteurs × 3
    u = rng.random((len(ids), n))
    states = (u[:, :, None] > B.cumsum(axis=1)[:, None, :]).sum(axis=2).clip(0, 2)

    veto = np.array([a["veto"] for a in data.actors])
    vp = np.array([P["veto_pass"][s] for s in STATES])
    pass_prob = np.prod(vp[states[veto]], axis=0) if veto.any() else np.ones(n)

    others = ~veto
    if others.any():
        w = np.array([a["influence"] for a in data.actors])[others]
        value = np.array([1.0, 0.0, -1.0])[states[others]]         # support / neutral / oppose
        score = (w[:, None] * value).sum(axis=0) / w.sum()
        c = P["support_curve"]
        support = 1 / (1 + np.exp(-(c["slope"] * score + c["offset"])))
    else:
        support = np.full(n, 0.5)
    return pass_prob * support


def posterior(data: DealData, as_of: str | None = None, hypothesis: dict[str, str] | None = None,
              exclude: set[int] = frozenset()) -> Posterior:
    """Positions des acteurs et probabilité de signature.

    hypothesis : {actor_id: "support" | "neutral" | "oppose"} pour fixer une position (simulate).
    exclude    : ids de signaux à ignorer (pour mesurer l'effet d'un signal).
    """
    as_of = as_of or clock.today().isoformat()
    beliefs = {a["id"]: belief(data, a["id"], as_of, exclude) for a in data.actors}
    for actor_id, state in (hypothesis or {}).items():
        beliefs[actor_id] = np.eye(3)[STATES.index(state)]
    draws = signature_draws(data, beliefs)
    lo, hi = np.quantile(draws, params()["interval"])
    return Posterior(beliefs, float(draws.mean()), float(lo), float(hi), float(draws.std()))


def simulate(data: DealData, hypothesis: dict[str, str], as_of: str | None = None) -> Posterior:
    """Probabilité si l'hypothèse était vraie (« si Sophie Lenoir passait favorable »)."""
    return posterior(data, as_of, hypothesis)


def history(data: DealData, dates: list[str]) -> list[Posterior]:
    """Probabilité à chaque date (signaux connus à cette date seulement)."""
    return [posterior(data, d) for d in dates]


def explain(data: DealData, signal_ids: list[int], as_of: str | None = None) -> list[dict]:
    """Effet de chaque signal sur la probabilité : on la recalcule sans lui."""
    base = posterior(data, as_of).p
    all_signals = {s["id"]: (a, s) for a, sigs in data.signals.items() for s in sigs}
    out = []
    for sid in signal_ids:
        if sid in all_signals:
            actor_id, s = all_signals[sid]
            delta = base - posterior(data, as_of, exclude={sid}).p
            out.append({"signal": s, "actor_id": actor_id, "delta": delta})
    return sorted(out, key=lambda d: -abs(d["delta"]))


def entropy(p: np.ndarray) -> float:
    p = p[p > 0]
    return float(-(p * np.log(p)).sum() / np.log(3))   # 0 = certain, 1 = aucune idée
