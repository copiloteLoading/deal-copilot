"""Construit data/past_lessons.json : les leçons des 20 contrats terminés du jeu de test
(retours d'expérience de eval/reviews.json, rédigés par eval/lessons_forecast.py).

Dans l'appli, ces leçons jouent le rôle des contrats passés du commercial : Muse Spark les lit pour
prévoir le contrat en cours et l'agent les cite dans son plan quand elles s'appliquent.

Usage : .\\.venv\\Scripts\\python.exe -m eval.past_lessons
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "past_lessons.json"


if __name__ == "__main__":
    reviews = json.loads((ROOT / "eval" / "reviews.json").read_text(encoding="utf-8"))
    out = []
    for name, folder in [("dev", "scenarios"), ("holdout", "scenarios_holdout")]:
        for r in reviews[name]:
            deal = json.loads((ROOT / "data" / folder / r["deal_id"] / "deal.json").read_text(encoding="utf-8"))
            out += [{"source_deal": r["deal_id"], "source_name": deal["name"], "outcome": x["outcome"],
                     "lesson": x["lesson"], "applies_when": x["applies_when"],
                     "evidence_quote": x["evidence_quote"]} for x in r["lessons"]]
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(out)} leçons écrites dans {OUT}")
