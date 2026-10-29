"""Test de cohérence : Muse Spark seul contre le modèle par acteur, sur le jeu de test.

Le Brier mesure si une probabilité est juste en moyenne. Ici on mesure si elle est digne de
confiance d'une semaine à l'autre, ce dont le commercial a besoin pour la suivre :
1. stabilité : la même entrée, 5 fois ; le chiffre bouge-t-il sans nouvelle information ?
2. monotonie : on ajoute au dernier débrief une phrase nette d'un détenteur de veto
   (« je suis contre » / « je soutiens ») ; la probabilité va-t-elle dans le bon sens ?
3. « et si ? » : la probabilité si ce veto était favorable (ou opposé), formulée de deux façons ;
   le chiffre dépend-il de la formulation ? va-t-il dans le bon sens ?

Points testés : réunions 2 et 4 de chaque contrat ; veto testé : celui de plus forte influence.
Le modèle reçoit le même fait sous forme de signal (ou d'hypothèse pour « et si ? »).

Usage : .\\.venv\\Scripts\\python.exe -m eval.consistency [holdout] [nombre de contrats]
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from copilot import extract, memory, model
from eval import baselines
from eval.evaluate import RESULTS, scenario_set, with_answers

N_DRAWS = 5
POINTS = [2, 4]           # réunions testées
NOISE_PTS = 0.10          # écart jugé visible par un commercial (10 points)

STATEMENT = {"oppose": "« je suis contre ce projet, je ne le validerai pas »",
             "support": "« je soutiens ce projet, je le validerai »"}
WHAT_IF = {  # deux formulations d'une même hypothèse
    "support": ["{name} now fully supports the project and will approve it.",
                "Imagine that {name} tells the rep, in the next meeting, that the project has "
                "their full backing and that they will sign off on it."],
    "oppose": ["{name} now opposes the project and will not approve it.",
               "Imagine that {name} tells the rep, in the next meeting, that they are against "
               "the project and will refuse to sign off on it."],
}


def injected(actor_id: str, stance: str, day: str) -> dict:
    """Le même fait que la phrase ajoutée au débrief, sous forme de signal pour le modèle."""
    return {"id": -1, "actor_id": actor_id, "date": day, "stance": stance, "strength": "strong",
            "source_type": "direct", "confidence": 0.9, "signal_type": "position"}


def run_scenario(folder) -> dict:
    conn = memory.connect(":memory:")
    deal_id = memory.import_deal(conn, folder)
    meetings = memory.meetings(conn, deal_id)
    for m in meetings:   # mêmes requêtes que l'évaluation : relu depuis le cache
        memory.add_signals(conn, deal_id, m["id"], extract.extract(m["transcript"], conn, deal_id)["signals"])
    deal = memory.get_deal(conn, deal_id)
    data = model.load(conn, deal_id)
    veto = max((a for a in data.actors if a["veto"]), key=lambda a: a["influence"])

    points = []
    for k in POINTS:
        day = meetings[k - 1]["date"]
        debriefs = [(mm["date"], mm["transcript"]) for mm in meetings[:k]]
        llm = lambda d=debriefs, h=None, tag=None: baselines.llm_probability(deal, d, h, tag)

        # 1. stabilité (tirage 0 = la requête de l'évaluation, déjà en cache)
        draws = [llm()] + [llm(tag=f"draw{i}") for i in range(1, N_DRAWS)]
        base_model = model.posterior(data, day).p
        rec = {"meeting": k, "veto": veto["id"], "llm_draws": draws,
               "model_draws": [model.posterior(data, day).p for _ in range(2)]}

        for stance in ("oppose", "support"):
            # 2. monotonie : une phrase nette ajoutée au dernier débrief
            last_day, last_text = debriefs[-1]
            extra = f"\nAh, et j'oubliais : en aparté, {veto['name']} m'a dit clairement {STATEMENT[stance]}."
            rec[f"llm_{stance}"] = llm(d=debriefs[:-1] + [(last_day, last_text + extra)])
            rec[f"model_{stance}"] = model.posterior(
                with_answers(data, [injected(veto["id"], stance, day)]), day).p
            # 3. « et si ? » formulé de deux façons
            rec[f"llm_if_{stance}"] = [llm(h=f.format(name=veto["name"])) for f in WHAT_IF[stance]]
            rec[f"model_if_{stance}"] = model.simulate(data, {veto["id"]: stance}, day).p
        rec["model"] = base_model
        points.append(rec)
    return {"deal_id": deal_id, "points": points}


def summarize(results: list[dict]) -> dict:
    pts = [p for r in results for p in r["points"]]
    out = {"n_points": len(pts)}
    for who in ("llm", "model"):
        base = [float(np.mean(p[f"{who}_draws"])) for p in pts]   # moyenne : le bruit ne compte pas comme erreur
        spread = [max(p[f"{who}_draws"]) - min(p[f"{who}_draws"]) for p in pts]
        mono = [(p[f"{who}_oppose"] < b < p[f"{who}_support"]) for p, b in zip(pts, base)]
        inverted = [p[f"{who}_oppose"] >= p[f"{who}_support"] for p in pts]
        if who == "llm":
            if_gap = [abs(a - b) for p in pts for a, b in [p["llm_if_support"], p["llm_if_oppose"]]]
            if_dir = [(p["llm_if_oppose"][i] <= b <= p["llm_if_support"][i])
                      for p, b in zip(pts, base) for i in range(2)]
        else:
            if_gap = [0.0 for _ in pts]   # une hypothèse est une entrée structurée : pas de formulation
            if_dir = [p["model_if_oppose"] <= b <= p["model_if_support"] for p, b in zip(pts, base)]
        out[who] = {"stability_std": float(np.mean([np.std(p[f"{who}_draws"]) for p in pts])),
                    "stability_range_mean": float(np.mean(spread)),
                    "stability_range_max": float(np.max(spread)),
                    "stability_visible": float(np.mean([s >= NOISE_PTS for s in spread])),
                    "monotone": float(np.mean(mono)), "inverted": float(np.mean(inverted)),
                    "move_oppose": float(np.mean([p[f"{who}_oppose"] - b for p, b in zip(pts, base)])),
                    "move_support": float(np.mean([p[f"{who}_support"] - b for p, b in zip(pts, base)])),
                    "what_if_gap_mean": float(np.mean(if_gap)), "what_if_gap_max": float(np.max(if_gap)),
                    "what_if_direction": float(np.mean(if_dir))}
    return out


def report(s: dict, results: list[dict]) -> str:
    L, M = s["llm"], s["model"]
    pct = lambda x: f"{x:.0%}"
    pts = lambda x: f"{100 * x:+.0f} pts" if x else "0"
    rows = [
        ("**Stabilité** : écart moyen entre le plus haut et le plus bas de 5 tirages",
         f"{100 * L['stability_range_mean']:.0f} pts", f"{100 * M['stability_range_mean']:.0f} pts"),
        ("Écart maximal sur 5 tirages", f"{100 * L['stability_range_max']:.0f} pts",
         f"{100 * M['stability_range_max']:.0f} pts"),
        (f"Points où le chiffre bouge d'au moins {100 * NOISE_PTS:.0f} pts sans nouvelle information",
         pct(L["stability_visible"]), pct(M["stability_visible"])),
        ("**Monotonie** : « contre » < aujourd'hui (moyenne des tirages) < « pour »", pct(L["monotone"]), pct(M["monotone"])),
        ("Ordre inversé (« contre » ≥ « pour »)", pct(L["inverted"]), pct(M["inverted"])),
        ("Effet moyen de « je suis contre »", pts(L["move_oppose"]), pts(M["move_oppose"])),
        ("Effet moyen de « je soutiens »", pts(L["move_support"]), pts(M["move_support"])),
        ("**« Et si ? »** : écart moyen entre deux formulations de la même hypothèse",
         f"{100 * L['what_if_gap_mean']:.0f} pts", "0 (par construction)"),
        ("Écart maximal entre deux formulations", f"{100 * L['what_if_gap_max']:.0f} pts", "0"),
        ("« Et si ? » dans le bon sens", pct(L["what_if_direction"]), pct(M["what_if_direction"])),
    ]
    lines = ["# Test de cohérence : Muse Spark seul contre le modèle", "",
             f"{len(results)} contrats, réunions {POINTS}, {s['n_points']} points de test. "
             f"Veto testé : celui de plus forte influence. Muse Spark : effort « low », {N_DRAWS} tirages.", "",
             "| Mesure | Muse Spark seul | Modèle |", "|---|---|---|"]
    lines += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    lines += ["", "## Détail", "", "| Contrat | Réunion | Muse Spark : 5 tirages | contre / pour | "
              "et si contre / et si pour (2 formulations) | Modèle : base, contre / pour |", "|---|---|---|---|---|---|"]
    f = lambda x: f"{x:.0%}"
    for r in results:
        for p in r["points"]:
            lines.append(
                f"| {r['deal_id']} | {p['meeting']} | {' '.join(map(f, p['llm_draws']))} | "
                f"{f(p['llm_oppose'])} / {f(p['llm_support'])} | "
                f"{' '.join(map(f, p['llm_if_oppose']))} / {' '.join(map(f, p['llm_if_support']))} | "
                f"{f(p['model'])}, {f(p['model_oppose'])} / {f(p['model_support'])} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    folders, suffix = scenario_set(sys.argv[1:])
    counts = [a for a in sys.argv[1:] if a.isdigit()]
    if counts:
        folders = folders[:int(counts[0])]
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(run_scenario, folders))
    summary = summarize(results)
    (RESULTS / f"consistency{suffix}.json").write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    text = report(summary, results)
    (RESULTS / f"consistency{suffix}.md").write_text(text, encoding="utf-8")
    print(text)
