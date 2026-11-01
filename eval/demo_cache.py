"""Construit data/demo_cache/ : les réponses de Muse du parcours d'exemple, publiées avec le dépôt
comme filet de sécurité (si l'API ne répond pas, l'appli reste utilisable sur ces entrées).

On rejoue le parcours de la vidéo exactement comme l'interface l'enchaîne, à une date fixe :
ouverture du dossier (extraction, prévision, plan), lecture des deux photos d'exemple, débrief
piège, réponse d'exemple à la question sur Sophie Lenoir, e-mail de suivi, ajout des notes
manuscrites et du tableau blanc, puis retour d'expérience de fin de contrat (issue « perdu »). Premier passage : appels réels pour ce qui manque. Second
passage, hors ligne : on note chaque réponse relue et on copie exactement celles-là.
Les réponses qui dépendent de la date du jour (débrief du jour, plan de l'agent) ne servent
que si l'appli tourne à cette même date (DEAL_COPILOT_TODAY).

Usage : .\\.venv\\Scripts\\python.exe -m eval.demo_cache
"""

from __future__ import annotations

import json
import os
import shutil
import sys

os.environ.setdefault("DEAL_COPILOT_TODAY", "2026-10-29")     # même date que la démo en ligne

from copilot import llm, memory, orgchart, photo, pipeline  # noqa: E402

TRAP = (pipeline.DEMO_DIR / "trap" / "debrief_piege.txt").read_text(encoding="utf-8")
EXPECTED = json.loads((pipeline.DEMO_DIR / "trap" / "truth.json").read_text(encoding="utf-8")
                      )["expected_agent_behavior"]
TRAP_ANSWER, CLOSING_NOTE = EXPECTED["rep_answer"], EXPECTED["closing_note"]
SAMPLES = pipeline.DEMO_DIR.parent.parent / "samples"


def read_photo(conn, deal_id: str, name: str) -> dict:
    deal = memory.get_deal(conn, deal_id)
    return photo.read((SAMPLES / name).read_bytes(), "image/jpeg", deal["name"],
                      [a["name"] for a in deal["actors"]])


def journey() -> None:
    """Le parcours de la vidéo, comme l'interface l'enchaîne."""
    conn = memory.connect(":memory:")
    d = pipeline.setup_demo(conn, reset=True)
    pipeline.state(conn, d)                    # prévision de Muse Spark sur l'historique
    pipeline.plan(conn, d)
    for name in ("notes_bank_meeting.jpg", "whiteboard_phasing.jpg"):
        read_photo(conn, d, name)              # lecture possible dès l'ouverture

    # débrief piège, question sur Sophie Lenoir, réponse d'exemple, e-mail
    pipeline.analyze_debrief(conn, d, TRAP)
    pipeline.state(conn, d)
    plan = pipeline.plan(conn, d)
    q = next((q for q in plan["questions"] if q["actor"]["id"] == "sophie_lenoir"), None)
    if q:
        pipeline.answer_question(conn, d, q, TRAP_ANSWER)
    st = pipeline.state(conn, d)
    acts = pipeline.refresh_actions(st, plan["actions"])
    if acts:
        pipeline.followup_email(st, acts[0])

    # notes manuscrites en photo, avec la nouvelle personne, puis tableau blanc
    for name in ("notes_bank_meeting.jpg", "whiteboard_phasing.jpg"):
        got = read_photo(conn, d, name)
        orgchart.apply(conn, d, [r for r in orgchart.propose(conn, d, got) if r["add"]])
        pipeline.analyze_debrief(conn, d, got["clean_notes"], got["date"] or None, f"Photo: {got['title']}")
        pipeline.state(conn, d)
        pipeline.plan(conn, d)

    # fin de contrat : le bilan, comme l'interface le demande par défaut (issue « perdu »)
    pipeline.review(conn, d, "lost", CLOSING_NOTE)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    journey()                                  # 1er passage : appels réels pour ce qui manque
    os.environ["LLM_PROVIDER"] = "offline"     # 2e passage : tout doit venir du cache
    llm.HITS = []
    journey()
    used = sorted(set(llm.HITS))
    shutil.rmtree(llm.DEMO_CACHE_DIR, ignore_errors=True)
    llm.DEMO_CACHE_DIR.mkdir(parents=True)
    for name in used:
        src = llm.CACHE_DIR / name if (llm.CACHE_DIR / name).exists() else None
        if src:
            shutil.copy(src, llm.DEMO_CACHE_DIR / name)
    size = sum(p.stat().st_size for p in llm.DEMO_CACHE_DIR.iterdir())
    print(f"{len(used)} réponses copiées dans {llm.DEMO_CACHE_DIR} ({size / 1e6:.1f} Mo)")
