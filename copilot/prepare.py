"""Préparer la prochaine réunion : qui sera là, ce qu'il faut obtenir de chacun, quoi demander.

Même schéma que l'agent : le modèle chiffre et classe, Muse Spark formule.
- Le modèle, pour chaque participant : position actuelle, incertitude, silence, ce que vaudrait
  une question (valeur de l'information) et ce que rapporterait de le voir sortir favorable
  (simulate). L'enjeu principal est le participant qui rapporte le plus.
- Le scénario « la réunion se passe bien » (tous les participants favorables) et le scénario
  « l'enjeu principal se ferme ».
- Les veto absents et incertains, à aborder indirectement.
- Muse Spark écrit, pour chaque participant, un objectif, une question à lui poser et un point
  d'attention, en citant les signaux. Aucun chiffre dans ses textes : l'interface affiche ceux du modèle.
"""

from __future__ import annotations

import re
from datetime import date

from copilot import decision, llm, model

SILENCE_DAYS = decision.SILENCE_DAYS

SCHEMA = {
    "type": "object",
    "properties": {
        "opening": {"type": "string"},
        "attendees": {"type": "array", "items": {"type": "object", "properties": {
            "actor_id": {"type": "string"},
            "objective": {"type": "string"},
            "question": {"type": "string"},
            "watch_out": {"type": "string"},
            "signal_ids": {"type": "array", "items": {"type": "integer"}}},
            "required": ["actor_id", "objective", "question", "watch_out", "signal_ids"],
            "additionalProperties": False}},
    },
    "required": ["opening", "attendees"],
    "additionalProperties": False,
}

RULES = """You help a sales rep prepare their next meeting on a multi-year infrastructure contract.
A probabilistic model has already ranked what is at stake with each attendee; you only phrase it.
For each attendee, in French:
- objective: what the rep should obtain from this person in this meeting, starting with a verb in
  the infinitive ("Obtenir...", "Faire confirmer...");
- question: one open question the rep can ask this person during the meeting, using "vous";
- watch_out: one short sentence on the risk or the condition to keep in mind.
Also write "opening": one sentence on the main stake of the meeting.
Rules: rely only on the recorded signals and facts given, and cite their ids. Never invent a fact.
Never write a number, a percentage or a probability: the interface shows the model's figures."""


def _days(since: str | None, as_of: str) -> int | None:
    return None if since is None else (date.fromisoformat(as_of) - date.fromisoformat(since)).days


def stakes(data: model.DealData, attendees: list[str], last_contact: dict[str, str | None],
           as_of: str | None = None) -> dict:
    """La partie chiffrée de la préparation, entièrement calculée par le modèle."""
    as_of = as_of or date.today().isoformat()
    base = model.posterior(data, as_of)
    actors = {a["id"]: a for a in data.actors}
    rows = []
    for aid in attendees:
        a = actors[aid]
        sigs = data.signals[aid]
        if_support = model.simulate(data, {aid: "support"}, as_of).p
        if_oppose = model.simulate(data, {aid: "oppose"}, as_of).p
        rows.append({
            "actor": a, "belief": base.beliefs[aid], "uncertainty": model.entropy(base.beliefs[aid]),
            "silence": _days(last_contact.get(aid), as_of),
            "condition": next((s for s in reversed(sigs) if s["stance"] == "conditional"), None),
            "last_signal": sigs[-1] if sigs else None,
            "question_gain": decision.question_value(data, base, aid, as_of)["gain"],
            "p_if_support": if_support, "p_if_oppose": if_oppose,
            "stake": if_support - if_oppose,                 # ce que la réunion peut faire basculer
        })
    rows.sort(key=lambda r: -r["stake"])
    best = model.simulate(data, {aid: "support" for aid in attendees}, as_of).p if attendees else base.p
    worst = rows[0]["p_if_oppose"] if rows else base.p
    absent = [a for a in data.actors if a["veto"] and a["id"] not in attendees
              and model.entropy(base.beliefs[a["id"]]) > 0.6]
    return {"as_of": as_of, "p_now": base.p, "low": base.low, "high": base.high,
            "p_best": best, "p_worst": worst, "attendees": rows, "absent_vetoes": absent}


def _facts(data: model.DealData, st: dict, meeting_day: str, title: str) -> str:
    orgs = {o["id"]: o["name"] for o in data.deal["organizations"]}
    lines = [f"Deal: {data.deal['name']} · buyer: {data.deal['buyer']} · rep: {data.deal['sales_rep']}",
             f"Upcoming meeting: {meeting_day} · {title}",
             "Attendees, ranked by what this meeting can change (most important first):"]
    for r in st["attendees"]:
        a, b = r["actor"], r["belief"]
        silence = "never met directly" if r["silence"] is None else f"last direct exchange {r['silence']} days ago"
        lines.append(f"- {a['id']} | {a['name']} | {a['role']} | {orgs.get(a['org_id'], '')} | "
                     f"{'VETO HOLDER' if a['veto'] else 'no veto'} | most likely stance: "
                     f"{model.STATES[int(b.argmax())]} | {silence}")
        lines += [f"    signal {s['id']} ({s['date']}, {s['stance']}): « {s['quote']} »"
                  for s in data.signals[a["id"]][-3:]]
    if st["absent_vetoes"]:
        lines.append("Uncertain veto holders NOT attending: "
                     + ", ".join(f"{a['name']} ({a['role']})" for a in st["absent_vetoes"]))
    return "\n".join(lines)


def _clean(text: str) -> str | None:
    """Les textes de Muse Spark ne doivent contenir aucun chiffre (sinon on les écarte)."""
    return None if not text or re.search(r"\d", text) else text.strip()


def _template(r: dict) -> dict:
    a = r["actor"]
    if r["condition"]:
        objective = f"Lever la condition posée par {a['name']}"
        watch = f"Condition en suspens : « {r['condition']['quote']} »"
    elif r["silence"] is None or r["silence"] > SILENCE_DAYS:
        objective = f"Renouer le contact direct avec {a['name']}"
        watch = "Peu d'échanges directs récents : sa position est mal connue."
    else:
        objective = f"Faire confirmer le soutien de {a['name']}"
        watch = "Vérifier que rien n'a changé depuis le dernier échange."
    return {"objective": objective, "question": "Où en êtes-vous de votre côté sur notre proposition ?",
            "watch_out": watch, "sources": [s for s in [r["condition"] or r["last_signal"]] if s]}


def prepare(data: model.DealData, attendees: list[str], last_contact: dict[str, str | None],
            meeting_day: str, title: str = "Réunion", as_of: str | None = None) -> dict:
    """Fiche de préparation complète : chiffres du modèle + textes de Muse Spark (ou gabarits)."""
    st = stakes(data, attendees, last_contact, as_of)
    signals = {s["id"]: s for sigs in data.signals.values() for s in sigs}
    texts, opening, fallback = {}, None, None
    try:
        out = llm.chat_json([{"role": "developer", "content": RULES},
                             {"role": "user", "content": _facts(data, st, meeting_day, title)}],
                            name="meeting_prep", schema=SCHEMA, **llm.effort("low"))
        opening = _clean(out.get("opening", ""))
        for item in out.get("attendees", []):
            if item.get("actor_id") not in attendees:
                continue
            fields = {k: _clean(item.get(k, "")) for k in ("objective", "question", "watch_out")}
            if all(fields.values()):
                texts[item["actor_id"]] = {**fields, "sources": [signals[i] for i in item.get("signal_ids", [])
                                                                  if i in signals]}
    except Exception as e:      # pas de réseau ou réponse invalide : on garde les gabarits
        fallback = str(e)
    for r in st["attendees"]:
        r.update(texts.get(r["actor"]["id"]) or _template(r))
        r["by_llm"] = r["actor"]["id"] in texts
    return {**st, "opening": opening, "meeting_day": meeting_day, "title": title, "fallback": fallback}
