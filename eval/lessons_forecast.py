"""Les leçons des contrats passés aident-elles Muse Spark à prévoir un nouveau contrat ?

1. Pour chaque contrat terminé des deux jeux, Muse Spark rédige le retour d'expérience
   (copilot/retro.py) à partir des débriefs, de l'issue et de la phrase du commercial sur ce qui a
   fait la différence (ici : l'explication de l'issue gardée dans la vérité cachée).
2. Validation croisée entre les jeux : on prévoit chaque réunion des contrats du jeu A avec les leçons
   du jeu B, et inversement. Aucune leçon ne vient du contrat prévu ni de son jeu.
3. Score de Brier sur la moyenne de 3 tirages, avec et sans leçons (mêmes débriefs, même consigne).

Usage : .\\.venv\\Scripts\\python.exe -m eval.lessons_forecast [n]   (n : contrats par jeu, pour tester)
Sortie : eval/lessons_forecast.md, eval/lessons_forecast.json, eval/reviews.json
"""

from __future__ import annotations

import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from copilot import memory, retro
from copilot.forecast import one_draw

ROOT = Path(__file__).resolve().parent.parent
RESULTS = Path(__file__).resolve().parent
SETS = {"dev": ROOT / "data" / "scenarios", "holdout": ROOT / "data" / "scenarios_holdout"}
TAGS = [None, "draw1", "draw2"]


def load(folder: Path) -> tuple[dict, list[tuple[str, str]], dict]:
    conn = memory.connect(":memory:")
    deal_id = memory.import_deal(conn, folder)
    texts = [(m["date"], m["transcript"]) for m in memory.meetings(conn, deal_id)]
    truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
    return memory.get_deal(conn, deal_id), texts, truth


def review_deal(folder: Path) -> dict:
    deal, texts, truth = load(folder)
    out = retro.review(deal, texts, truth["outcome"], truth["outcome_explanation"])
    return {"deal_id": deal["id"], **out}


def mean_draw(deal, texts, lessons=None) -> float:
    return float(np.mean([one_draw(deal, texts, cache_tag=t, lessons=lessons)["probability"] for t in TAGS]))


def forecast_deal(folder: Path, lessons: str) -> dict:
    deal, texts, truth = load(folder)
    records = [{"meeting": k + 1, "none": mean_draw(deal, texts[:k + 1]),
                "lessons": mean_draw(deal, texts[:k + 1], lessons)} for k in range(len(texts))]
    return {"deal_id": deal["id"], "y": 1 if truth["outcome"] == "signed" else 0, "records": records}


def brier(results, method, meetings=None) -> float:
    return float(np.mean([(r[method] - d["y"]) ** 2 for d in results for r in d["records"]
                          if meetings is None or r["meeting"] in meetings]))


def gain_interval(results, n=2000) -> tuple[float, float]:
    rng = random.Random(0)
    per = [[(r["none"] - d["y"]) ** 2 - (r["lessons"] - d["y"]) ** 2 for r in d["records"]] for d in results]
    stats = [np.mean([x for d in (rng.choice(per) for _ in per) for x in d]) for _ in range(n)]
    return float(np.percentile(stats, 5)), float(np.percentile(stats, 95))


def report(by_set: dict, n_lessons: dict) -> str:
    lines = ["# Les leçons des contrats passés aident-elles Muse Spark à prévoir ?", "",
             "Validation croisée : les contrats de chaque jeu sont prévus avec les leçons tirées de l'autre jeu. "
             "Probabilité = moyenne de 3 tirages. Score de Brier : plus bas = meilleur. "
             "Gain = Brier sans leçons − Brier avec ; intervalle à 90 % par bootstrap sur les contrats.", "",
             "| Jeu prévu | Leçons utilisées | Brier sans leçons | Brier avec leçons | Gain | Intervalle à 90 % |",
             "|---|---|---|---|---|---|"]
    rows = list(by_set.items()) + [("les deux", sum(by_set.values(), []))]
    for name, res in rows:
        lo, hi = gain_interval(res)
        used = n_lessons.get(name, sum(n_lessons.values()))
        lines.append(f"| {name} ({sum(len(d['records']) for d in res)} prévisions) | {used} | "
                     f"{brier(res, 'none'):.3f} | {brier(res, 'lessons'):.3f} | "
                     f"{brier(res, 'none') - brier(res, 'lessons'):+.3f} | [{lo:+.3f} ; {hi:+.3f}] |")
    both = rows[-1][1]
    lines += ["", "Par réunion (les deux jeux) :", "", "| Réunion | Sans leçons | Avec leçons |", "|---|---|---|"]
    for k in sorted({r["meeting"] for d in both for r in d["records"]}):
        lines.append(f"| {k} | {brier(both, 'none', {k}):.3f} | {brier(both, 'lessons', {k}):.3f} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    folders = {s: sorted(p for p in root.iterdir() if (p / "deal.json").exists())[:limit]
               for s, root in SETS.items()}
    with ThreadPoolExecutor(max_workers=5) as pool:
        reviews = {s: list(pool.map(review_deal, f)) for s, f in folders.items()}
    lessons = {s: retro.lessons_text([x for r in reviews[s] for x in r["lessons"]]) for s in SETS}
    other = {"dev": "holdout", "holdout": "dev"}
    with ThreadPoolExecutor(max_workers=5) as pool:
        by_set = {s: list(pool.map(lambda f: forecast_deal(f, lessons[other[s]]), folders[s])) for s in SETS}
    n_lessons = {s: sum(len(r["lessons"]) for r in reviews[other[s]]) for s in SETS}
    text = report(by_set, n_lessons)
    if limit is None:
        (RESULTS / "reviews.json").write_text(json.dumps(reviews, ensure_ascii=False, indent=2), encoding="utf-8")
        (RESULTS / "lessons_forecast.json").write_text(json.dumps(by_set, indent=2), encoding="utf-8")
        (RESULTS / "lessons_forecast.md").write_text(text, encoding="utf-8")
    print(text)
    print(lessons["dev"][:2000])
