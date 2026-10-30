"""Les 2 questions du copilote améliorent-elles la prévision de Muse Spark ?

Dans le produit, la probabilité affichée vient de Muse Spark (copilot/forecast.py) et les réponses
du commercial aux questions sont ajoutées au dossier comme un compte rendu de plus
(« Question: ... / Answer: ... »). On mesure ici exactement cela, sur le jeu de test.

Pour chaque contrat et chaque réunion k, on reprend les acteurs interrogés par chaque stratégie
dans eval/results[_holdout].json (mêmes choix que l'évaluation du modèle) :
    voi     valeur de l'information (le choix du copilote) ;
    llm     les 2 acteurs que Muse Spark seul choisirait ;
    random  2 acteurs au hasard.
La réponse du commercial est simulée avec la vérité cachée (position réelle à la date k), en une
phrase. Les réponses s'accumulent d'une réunion à l'autre, comme dans le produit. Muse Spark relit
débriefs + réponses et donne sa probabilité (un tirage, même consigne que le produit).

Usage : .\\.venv\\Scripts\\python.exe -m eval.questions_forecast
Sortie : eval/questions_forecast.md et .json
"""

from __future__ import annotations

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from copilot import memory
from copilot.forecast import one_draw

ROOT = Path(__file__).resolve().parent.parent
RESULTS = Path(__file__).resolve().parent
SETS = {"dev": (ROOT / "data" / "scenarios", RESULTS / "results.json"),
        "holdout": (ROOT / "data" / "scenarios_holdout", RESULTS / "results_holdout.json")}
STRATEGIES = ["voi", "llm", "random"]
LABELS = {"none": "Aucune question (Muse Spark seul)", "voi": "Questions du copilote (valeur de l'information)",
          "llm": "Questions choisies par Muse Spark seul", "random": "Questions au hasard"}

ANSWER = {"support": "{name} soutient le projet.",
          "neutral": "{name} n'a pas encore de position arrêtée.",
          "oppose": "{name} est contre en l'état."}


def answer_text(actor: dict, stance: str) -> str:
    """Ce que le produit enregistre après une réponse : la question puis la réponse du commercial."""
    return (f"Question: Where does {actor['name']} ({actor['role']}) stand today?\n"
            f"Answer: {ANSWER[stance].format(name=actor['name'])}")


def run_deal(folder: Path, saved: dict) -> dict:
    truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
    conn = memory.connect(":memory:")
    deal_id = memory.import_deal(conn, folder)
    deal = memory.get_deal(conn, deal_id)
    actors = {a["id"]: a for a in deal["actors"]}
    meetings = memory.meetings(conn, deal_id)
    texts = {s: [] for s in STRATEGIES}
    records = []
    for k, m in enumerate(meetings):
        day, real, rec = m["date"], truth["positions"][k]["stances"], saved["records"][k]
        debrief = (day, m["transcript"])
        out = {"meeting": k + 1, "none": rec["llm"]}          # sans question : déjà mesuré (même cache)
        for s in STRATEGIES:
            texts[s].append(debrief)
            texts[s] += [(day, answer_text(actors[a], real[a])) for a in rec[f"picks_{s}"]]
            out[s] = one_draw(deal, list(texts[s]))["probability"]
        records.append(out)
    return {"deal_id": deal_id, "y": 1 if truth["outcome"] == "signed" else 0, "records": records}


def brier(results: list[dict], method: str) -> float:
    return float(np.mean([(r[method] - d["y"]) ** 2 for d in results for r in d["records"]]))


def gain_interval(results: list[dict], method: str, n: int = 2000) -> tuple[float, float]:
    """Intervalle à 90 % du gain de Brier (aucune question − méthode), par bootstrap sur les contrats."""
    rng = random.Random(0)
    per_deal = [[(r["none"] - d["y"]) ** 2 - (r[method] - d["y"]) ** 2 for r in d["records"]] for d in results]
    stats = []
    for _ in range(n):
        pick = [rng.choice(per_deal) for _ in per_deal]
        stats.append(np.mean([x for deal in pick for x in deal]))
    return float(np.percentile(stats, 5)), float(np.percentile(stats, 95))


def report(by_set: dict[str, list[dict]]) -> str:
    lines = ["# Les questions du copilote améliorent-elles la prévision de Muse Spark ?", "",
             "Réponses du commercial simulées avec la vérité cachée, ajoutées au dossier comme dans le "
             "produit ; Muse Spark relit tout et donne sa probabilité. Score de Brier : plus bas = meilleur. "
             "Gain = Brier sans question − Brier avec ; intervalle à 90 % par bootstrap sur les contrats.", ""]
    for name, results in list(by_set.items()) + [("dev + holdout", sum(by_set.values(), []))]:
        n = sum(len(d["records"]) for d in results)
        lines += [f"## Jeu {name} ({len(results)} contrats, {n} prévisions)", "",
                  "| Questions | Brier | Gain | Intervalle à 90 % |", "|---|---|---|---|",
                  f"| {LABELS['none']} | {brier(results, 'none'):.3f} | — | — |"]
        for s in STRATEGIES:
            lo, hi = gain_interval(results, s)
            lines.append(f"| {LABELS[s]} | {brier(results, s):.3f} | "
                         f"{brier(results, 'none') - brier(results, s):+.3f} | [{lo:+.3f} ; {hi:+.3f}] |")
        lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    only = sys.argv[1:]                                        # ex. : dev 2  → 2 contrats du jeu dev
    by_set = {}
    for name, (root, saved_file) in SETS.items():
        if only and only[0] != name:
            continue
        saved = {d["deal_id"]: d for d in json.loads(saved_file.read_text(encoding="utf-8"))["results"]}
        folders = sorted(p for p in root.iterdir() if (p / "deal.json").exists())
        if len(only) > 1:
            folders = folders[:int(only[1])]
        with ThreadPoolExecutor(max_workers=5) as pool:
            by_set[name] = list(pool.map(lambda f: run_deal(f, saved[f.name]), folders))
    text = report(by_set)
    if not only:
        (RESULTS / "questions_forecast.json").write_text(json.dumps(by_set, indent=2), encoding="utf-8")
        (RESULTS / "questions_forecast.md").write_text(text, encoding="utf-8")
    print(text)
