"""Évaluation du copilote sur le jeu de test (data/scenarios), réunion par réunion.

Pour chaque contrat et chaque réunion k :
- extraction des signaux du débrief k (Muse Spark) et comparaison à ce que le débrief exprime (gold) ;
- probabilité de signature selon :
    llm      Muse Spark seul, qui lit les débriefs 1..k ;
    model    le modèle par acteur, nourri par l'extraction, sans question ;
    q_voi    l'hybride : le modèle + 2 questions choisies par la valeur de l'information ;
    q_llm    le modèle + 2 questions sur les acteurs que choisit Muse Spark seul ;
    q_random le modèle + 2 questions sur des acteurs tirés au hasard ;
  les réponses du commercial sont simulées avec la vérité cachée (position réelle à la date k) ;
- justesse des positions : part des acteurs dont la position la plus probable est la vraie.

Issue : 1 si le contrat est signé, 0 s'il est perdu ou retardé. Score de Brier = moyenne de (p - issue)².

Usage : .\\.venv\\Scripts\\python.exe -m eval.evaluate [holdout]
Autre version des paramètres : $env:MODEL_PARAMS="config/model_params_asym.yaml"
Sorties : eval/results[_holdout][_asym].md et .json
"""

from __future__ import annotations

import json
import os
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from copilot import decision, extract, memory, model
from eval import baselines

ROOT = Path(__file__).resolve().parent.parent
SCENARIOS = ROOT / "data" / "scenarios"
RESULTS = Path(__file__).resolve().parent
STRATEGIES = ["voi", "llm", "random"]
N_QUESTIONS = 2
DETECT = 0.30          # seuil d'alerte : en dessous, le contrat est signalé « en danger »
LENIENT = {"conditional": "neutral"}


def answer_signal(uid: int, actor_id: str, stance: str, day: str) -> dict:
    """Réponse simulée du commercial : la position réelle de l'acteur, rapportée nettement."""
    return {"id": uid, "actor_id": actor_id, "date": day, "stance": stance, "strength": "strong",
            "source_type": "reported", "confidence": 0.9, "signal_type": "information"}


def with_answers(data: model.DealData, answers: list[dict]) -> model.DealData:
    signals = {a: list(v) for a, v in data.signals.items()}
    for s in answers:
        signals[s["actor_id"]].append(s)
    for a in signals:   # tri stable : une réponse passe après les signaux du même jour
        signals[a].sort(key=lambda s: s["date"])
    return model.DealData(data.deal, data.actors, signals, data.org_types)


def accuracy(beliefs: dict, truth: dict) -> float:
    return float(np.mean([model.STATES[int(beliefs[a].argmax())] == s for a, s in truth.items()]))


def extracted_pairs(signals: list[dict]) -> dict[str, str]:
    """Position exprimée par acteur dans un débrief (le dernier signal informatif l'emporte)."""
    out = {}
    for s in signals:
        if s["actor_id"] and s["stance"] != "unknown" and s["signal_type"] != "deadline":
            out[s["actor_id"]] = s["stance"]
    return out


def run_scenario(folder: Path) -> dict:
    truth = json.loads((folder / "truth.json").read_text(encoding="utf-8"))
    gold = json.loads((folder / "gold.json").read_text(encoding="utf-8"))
    conn = memory.connect(":memory:")
    deal_id = memory.import_deal(conn, folder)
    meetings = memory.meetings(conn, deal_id)

    for m in meetings:
        result = extract.extract(m["transcript"], conn, deal_id)
        memory.add_signals(conn, deal_id, m["id"], result["signals"])
    deal = memory.get_deal(conn, deal_id)
    data = model.load(conn, deal_id)
    all_signals = memory.signals(conn, deal_id)
    actor_ids = [a["id"] for a in data.actors]
    y = 1 if truth["outcome"] == "signed" else 0

    rng = random.Random(deal_id)
    answers = {s: [] for s in STRATEGIES}
    uid, records, extraction = 0, [], []
    for k, m in enumerate(meetings):
        day, real = m["date"], truth["positions"][k]["stances"]
        debriefs = [(mm["date"], mm["transcript"]) for mm in meetings[:k + 1]]

        found = extracted_pairs([s for s in all_signals if s["meeting_id"] == m["id"]])
        expected = {g["actor_id"]: g["stance_expressed"] for g in gold[k]["mentions"]}
        extraction.append({"found": found, "expected": expected})

        base = model.posterior(data, day)
        rec = {"meeting": k + 1, "date": day, "model": base.p, "model_std": base.std,
               "acc_model": accuracy(base.beliefs, real),
               "llm": baselines.llm_probability(deal, debriefs)}
        for strat in STRATEGIES:
            current = with_answers(data, answers[strat])
            if strat == "voi":
                picks = [q["actor"]["id"] for q in
                         decision.rank_questions(current, {}, day, k=N_QUESTIONS, min_gain=0)]
            elif strat == "llm":
                picks = baselines.llm_pick_actors(deal, debriefs, N_QUESTIONS)
            else:
                picks = rng.sample(actor_ids, N_QUESTIONS)
            for a in picks:
                uid -= 1
                answers[strat].append(answer_signal(uid, a, real[a], day))
            after = model.posterior(with_answers(data, answers[strat]), day)
            rec.update({f"q_{strat}": after.p, f"std_{strat}": after.std,
                        f"acc_{strat}": accuracy(after.beliefs, real), f"picks_{strat}": picks,
                        f"veto_picks_{strat}": sum(1 for a in picks
                                                   if next(x for x in data.actors if x["id"] == a)["veto"])})
        records.append(rec)
    return {"deal_id": deal_id, "outcome": truth["outcome"], "y": y, "records": records,
            "extraction": extraction}


# ------------------------------------------------------------------ agrégation
METHODS = {"llm": "Muse Spark seul", "model": "Modèle seul (sans question)",
           "q_voi": "Hybride : modèle + 2 questions (valeur de l'information)",
           "q_llm": "Modèle + 2 questions choisies par Muse Spark seul",
           "q_random": "Modèle + 2 questions au hasard"}


def brier(results: list[dict], method: str, meetings: set[int] | None = None) -> float:
    errs = [(r[method] - s["y"]) ** 2 for s in results for r in s["records"]
            if meetings is None or r["meeting"] in meetings]
    return float(np.mean(errs))


def extraction_scores(results: list[dict], lenient: bool) -> dict:
    tp = n_found = n_expected = actor_hits = 0
    for s in results:
        for e in s["extraction"]:
            f = {a: LENIENT.get(v, v) if lenient else v for a, v in e["found"].items()}
            g = {a: LENIENT.get(v, v) if lenient else v for a, v in e["expected"].items()}
            tp += sum(1 for a, v in f.items() if g.get(a) == v)
            actor_hits += sum(1 for a in g if a in f)
            n_found, n_expected = n_found + len(f), n_expected + len(g)
    return {"precision": tp / max(n_found, 1), "recall": tp / max(n_expected, 1),
            "actors_found": actor_hits / max(n_expected, 1)}


def first_alert(records: list[dict], method: str) -> int | None:
    return next((r["meeting"] for r in records if r[method] < DETECT), None)


def summarize(results: list[dict]) -> dict:
    n_meetings = max(r["meeting"] for s in results for r in s["records"])
    summary = {"n_deals": len(results), "n_forecasts": sum(len(s["records"]) for s in results),
               "outcomes": {o: sum(s["outcome"] == o for s in results) for o in ("signed", "lost", "delayed")},
               "brier": {m: {"all": brier(results, m), "early": brier(results, m, {1, 2}),
                             "last": brier(results, m, {n_meetings})} for m in METHODS},
               "extraction": {"exact": extraction_scores(results, False),
                              "lenient": extraction_scores(results, True)},
               "positions": {k: float(np.mean([r[k] for s in results for r in s["records"]]))
                             for k in ["acc_model", "acc_voi", "acc_llm", "acc_random"]},
               "uncertainty": {k: float(np.mean([r[k] for s in results for r in s["records"]]))
                               for k in ["model_std", "std_voi", "std_llm", "std_random"]},
               "veto_share": {s_: float(np.mean([r[f"veto_picks_{s_}"] / N_QUESTIONS
                                                 for s in results for r in s["records"]]))
                              for s_ in STRATEGIES}}
    detection = {}
    for m in ["llm", "model", "q_voi"]:
        lost = [s for s in results if s["y"] == 0]
        signed = [s for s in results if s["y"] == 1]
        alerts = [first_alert(s["records"], m) for s in lost]
        detection[m] = {"failed_deals_flagged": sum(a is not None for a in alerts),
                        "n_failed": len(lost),
                        "mean_first_alert_meeting": (float(np.mean([a for a in alerts if a]))
                                                     if any(alerts) else None),
                        "signed_deals_falsely_flagged": sum(first_alert(s["records"], m) is not None
                                                            for s in signed)}
    summary["detection"] = detection
    return summary


def report(summary: dict, results: list[dict]) -> str:
    s = summary
    lines = ["# Résultats de l'évaluation", "",
             f"{s['n_deals']} contrats fictifs générés par Muse Spark ({s['outcomes']['signed']} signés, "
             f"{s['outcomes']['lost']} perdus, {s['outcomes']['delayed']} retardés), "
             f"{s['n_forecasts']} prévisions (une par réunion). Issue = 1 si signé, 0 sinon.",
             "Les réponses du commercial aux questions sont simulées avec la vérité cachée.", "",
             "## Score de Brier (plus bas = meilleur ; 0,25 = toujours répondre 50 %)", "",
             "| Méthode | Toutes réunions | Réunions 1-2 | Dernière réunion |", "|---|---|---|---|"]
    for m, label in METHODS.items():
        b = s["brier"][m]
        lines.append(f"| {label} | {b['all']:.3f} | {b['early']:.3f} | {b['last']:.3f} |")
    e = s["extraction"]
    lines += ["", "## Extraction des signaux (Muse Spark)", "",
              "| | Précision | Rappel | Acteurs retrouvés |", "|---|---|---|---|",
              f"| Position exacte | {e['exact']['precision']:.0%} | {e['exact']['recall']:.0%} | "
              f"{e['exact']['actors_found']:.0%} |",
              f"| Conditionnel = neutre | {e['lenient']['precision']:.0%} | "
              f"{e['lenient']['recall']:.0%} | {e['lenient']['actors_found']:.0%} |",
              "", "## Utilité des questions", "",
              "| Questions | Positions justes | Incertitude (écart-type) | Part de veto interrogés |",
              "|---|---|---|---|",
              f"| Aucune | {s['positions']['acc_model']:.0%} | {s['uncertainty']['model_std']:.3f} | — |"]
    for strat, label in [("voi", "Valeur de l'information (hybride)"), ("llm", "Choisies par Muse Spark seul"),
                         ("random", "Au hasard")]:
        lines.append(f"| {label} | {s['positions'][f'acc_{strat}']:.0%} | "
                     f"{s['uncertainty'][f'std_{strat}']:.3f} | {s['veto_share'][strat]:.0%} |")
    lines += ["", f"## Détection des contrats non signés (alerte si probabilité < {DETECT:.0%})", "",
              "| Méthode | Contrats non signés repérés | Réunion de la première alerte (moyenne) | "
              "Fausses alertes sur des contrats signés |", "|---|---|---|---|"]
    for m in ["llm", "model", "q_voi"]:
        d = s["detection"][m]
        first = f"{d['mean_first_alert_meeting']:.1f}" if d["mean_first_alert_meeting"] else "—"
        lines.append(f"| {METHODS[m]} | {d['failed_deals_flagged']} / {d['n_failed']} | {first} | "
                     f"{d['signed_deals_falsely_flagged']} |")
    lines += ["", "## Détail par contrat", "", "| Contrat | Issue | Muse Spark seul | Modèle seul | Hybride |",
              "|---|---|---|---|---|"]
    for r in results:
        traj = {m: " → ".join(f"{x[m]:.0%}" for x in r["records"]) for m in ["llm", "model", "q_voi"]}
        lines.append(f"| {r['deal_id']} | {r['outcome']} | {traj['llm']} | {traj['model']} | {traj['q_voi']} |")
    return "\n".join(lines) + "\n"


def scenario_set(args: list[str]) -> tuple[list[Path], str]:
    """Dossiers du jeu demandé et suffixe des fichiers de résultats."""
    holdout = "holdout" in args
    root = SCENARIOS.parent / "scenarios_holdout" if holdout else SCENARIOS
    suffix = "_holdout" if holdout else ""
    if os.environ.get("MODEL_PARAMS"):
        suffix += "_" + Path(os.environ["MODEL_PARAMS"]).stem.replace("model_params_", "")
    return sorted(p for p in root.iterdir() if (p / "deal.json").exists()), suffix


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    folders, suffix = scenario_set(sys.argv[1:])
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(run_scenario, folders))
    summary = summarize(results)
    (RESULTS / f"results{suffix}.json").write_text(
        json.dumps({"summary": summary, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    text = report(summary, results)
    (RESULTS / f"results{suffix}.md").write_text(text, encoding="utf-8")
    print(text)
