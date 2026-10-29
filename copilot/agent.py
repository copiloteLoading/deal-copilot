"""L'agent : « le LLM propose, le modèle tranche ».

Muse Spark reçoit l'état du dossier et quatre outils :
  get_signals(actor_id)        les signaux d'un acteur, avec leur citation exacte (mémoire)
  evaluate_question(actor_id)  ce que gagnerait une question sur cet acteur (modèle)
  simulate_action(effects)     la probabilité si une action réussissait (modèle)
  submit_plan(...)             rend le plan : au plus 2 questions, des actions
Il propose librement (y compris des actions créatives), mais chaque chiffre vient d'un outil.

Après la boucle, on ne fait pas confiance au plan tel quel : finalize() vérifie les acteurs et
les citations, rejette tout texte contenant un chiffre, recalcule chaque valeur avec le modèle
et classe selon le modèle. Sans réseau ou en cas d'échec, on retombe sur les gabarits de decision.py.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date

from copilot import decision, llm, memory, model

MAX_STEPS = 8          # tours de boucle au plus : évite les boucles coûteuses
MAX_QUESTIONS = 2
MAX_ACTIONS = 4
MIN_GAIN = 0.01        # en dessous, une question n'apporte presque rien

EFFECTS_SCHEMA = {
    "type": "array",
    "items": {"type": "object",
              "properties": {"actor_id": {"type": "string"},
                             "stance": {"type": "string", "enum": model.STATES}},
              "required": ["actor_id", "stance"], "additionalProperties": False}}

TOOLS = [
    {"type": "function", "function": {
        "name": "get_signals",
        "description": "List every signal recorded about one actor: id, date, stance, strength, "
                       "source and the exact quote from the debrief.",
        "parameters": {"type": "object", "properties": {"actor_id": {"type": "string"}},
                       "required": ["actor_id"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "evaluate_question",
        "description": "Ask the deal model how much a question about this actor would reduce the "
                       "uncertainty on the signature probability (in percentage points).",
        "parameters": {"type": "object", "properties": {"actor_id": {"type": "string"}},
                       "required": ["actor_id"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "simulate_action",
        "description": "Ask the deal model for the signature probability if an action succeeded, "
                       "described as the stances the targeted actors would take.",
        "parameters": {"type": "object", "properties": {"effects": EFFECTS_SCHEMA},
                       "required": ["effects"], "additionalProperties": False}}},
    {"type": "function", "function": {
        "name": "submit_plan",
        "description": "Submit the final plan. Call it exactly once, at the end.",
        "parameters": {"type": "object", "properties": {
            "questions": {"type": "array", "items": {"type": "object", "properties": {
                "actor_id": {"type": "string"},
                "text": {"type": "string"},
                "signal_ids": {"type": "array", "items": {"type": "integer"}}},
                "required": ["actor_id", "text", "signal_ids"], "additionalProperties": False}},
            "actions": {"type": "array", "items": {"type": "object", "properties": {
                "title": {"type": "string"},
                "rationale": {"type": "string"},
                "effects": EFFECTS_SCHEMA,
                "signal_ids": {"type": "array", "items": {"type": "integer"}}},
                "required": ["title", "rationale", "effects", "signal_ids"],
                "additionalProperties": False}}},
            "required": ["questions", "actions"], "additionalProperties": False}}},
]

RULES = f"""You are the strategy assistant of a sales rep negotiating a multi-year infrastructure
contract. A probabilistic deal model tracks each actor's hidden position (support / neutral / oppose)
and computes the signature probability. Veto holders must all let the deal pass.

Your job, using the tools:
1. Find the actors whose position matters most and is most uncertain (veto holders first).
   Read their signals with get_signals when useful.
2. Check candidate questions with evaluate_question. Keep at most {MAX_QUESTIONS} questions, the ones the
   model values most; drop any that reduces uncertainty by less than {MIN_GAIN * 100:.0f} point.
3. Propose 3 to {MAX_ACTIONS} concrete actions, including creative ones (for example a payment schedule
   backed by a bank guarantee), each described by the stances the targeted actors would take if it
   succeeds. Check each with simulate_action.
4. Call submit_plan.

Rules:
- Never invent a fact. Every question and action must rely on recorded signals: cite their ids.
- Questions are asked TO THE REP right after the meeting, to learn what the rep already knows
  or noticed (not tasks to do later). Write them as real questions in French, using "vous",
  answerable in one sentence. Each question must aim at the actor's real position, or at what
  could make them block the deal. Example: "Savez-vous si le projet est déjà inscrit au budget de
  Baltis Telecom ?" Never "Demandez à X...".
- Action titles start with a verb in the infinitive ("Proposer...", "Organiser..."); rationales are
  one short sentence in French explaining which recorded signal makes the action useful.
- Never write a number, a percentage or a probability in any text: the interface shows the
  model's figures next to your text.
- Use the tools; you have at most {MAX_STEPS} rounds."""


def _state_message(conn, deal_id: str, data: model.DealData, base: model.Posterior, as_of: str) -> str:
    deal = data.deal
    orgs = {o["id"]: o["name"] for o in deal["organizations"]}
    contact = memory.last_contact(conn, deal_id)
    lines = [f"Deal: {deal['name']} · buyer: {deal['buyer']} · seller: {deal['seller']} · "
             f"rep: {deal['sales_rep']} · today: {as_of}",
             f"Signature probability now: {base.p:.0%} (80% interval {base.low:.0%}-{base.high:.0%})",
             "", "Actors (id | name | role | organization | veto | influence | P(support/neutral/oppose)"
                 " | days since last direct exchange):"]
    for a in data.actors:
        b = base.beliefs[a["id"]]
        d = contact.get(a["id"])
        days = "never" if d is None else (date.fromisoformat(as_of) - date.fromisoformat(d)).days
        lines.append(f"- {a['id']} | {a['name']} | {a['role']} | {orgs.get(a['org_id'], '')} | "
                     f"{'VETO' if a['veto'] else '-'} | {a['influence']:.2f} | "
                     f"{b[0]:.2f}/{b[1]:.2f}/{b[2]:.2f} | {days}")
    meetings = memory.meetings(conn, deal_id)
    if meetings:
        last = meetings[-1]
        lines += ["", f"Latest meeting ({last['date']}, {last['title']}): {last['summary'] or ''}"]
        sigs = [s for s in memory.signals(conn, deal_id) if s["meeting_id"] == last["id"]]
        lines.append("Signals of that meeting (id | actor | stance | quote):")
        lines += [f"- {s['id']} | {s['actor_id'] or s['raw_name']} | {s['stance']} | « {s['quote']} »"
                  for s in sigs]
    return "\n".join(lines)


class Tools:
    """Exécute les outils de l'agent sur le modèle et la mémoire, et garde une trace lisible."""

    def __init__(self, data: model.DealData, base: model.Posterior, as_of: str):
        self.data, self.base, self.as_of = data, base, as_of
        self.actor_ids = {a["id"] for a in data.actors}
        self.trace: list[dict] = []

    def run(self, name: str, args: dict) -> dict:
        try:
            result = getattr(self, name)(**args)
        except Exception as e:   # l'agent doit voir l'erreur et corriger, pas faire planter l'appli
            result = {"error": str(e)}
        self.trace.append({"tool": name, "args": args, "result": result})
        return result

    def _check(self, actor_id: str) -> None:
        if actor_id not in self.actor_ids:
            raise ValueError(f"unknown actor_id {actor_id!r}; use one of {sorted(self.actor_ids)}")

    def get_signals(self, actor_id: str) -> dict:
        self._check(actor_id)
        return {"signals": [{"id": s["id"], "date": s["date"], "stance": s["stance"],
                             "strength": s.get("strength"), "source": s.get("source_type"),
                             "quote": s["quote"]} for s in self.data.signals[actor_id]]}

    def evaluate_question(self, actor_id: str) -> dict:
        self._check(actor_id)
        v = decision.question_value(self.data, self.base, actor_id, self.as_of)
        return {"uncertainty_reduction_points": round(float(v["gain"]) * 100, 1),
                "expected_interval_after_answer": [round(float(v["expected_low"]) * 100),
                                                   round(float(v["expected_high"]) * 100)]}

    def simulate_action(self, effects: list[dict]) -> dict:
        fx = _effects(effects, self.actor_ids)
        if not fx:
            raise ValueError("effects must name at least one known actor")
        v = decision.action_value(self.data, self.base, fx, self.as_of)
        return {"probability_now_percent": round(v["p_before"] * 100),
                "probability_if_success_percent": round(v["p_after"] * 100)}

    def submit_plan(self, questions: list, actions: list) -> dict:
        return {"received": True}


def _effects(effects: list[dict], actor_ids: set[str]) -> dict[str, str]:
    return {e["actor_id"]: e["stance"] for e in effects
            if e.get("actor_id") in actor_ids and e.get("stance") in model.STATES}


def _has_number(text: str) -> bool:
    return bool(re.search(r"\d", text or ""))


def finalize(data: model.DealData, plan: dict, as_of: str) -> dict:
    """Vérifie le plan proposé par Muse Spark et le chiffre avec le modèle (qui a le dernier mot)."""
    base = model.posterior(data, as_of)
    actors = {a["id"]: a for a in data.actors}
    signals = {s["id"]: s for sigs in data.signals.values() for s in sigs}
    rejected = []

    questions, seen = [], set()
    for q in plan.get("questions", []):
        a = actors.get(q.get("actor_id"))
        if a is None or a["id"] in seen or not q.get("text") or _has_number(q["text"]):
            rejected.append({"kind": "question", "item": q, "reason": "acteur inconnu, doublon ou chiffre"})
            continue
        v = decision.question_value(data, base, a["id"], as_of)
        if v["gain"] < MIN_GAIN:
            rejected.append({"kind": "question", "item": q, "reason": "gain négligeable selon le modèle"})
            continue
        cited = [signals[i] for i in q.get("signal_ids", []) if i in signals]
        seen.add(a["id"])
        questions.append({"actor": a, "text": q["text"], "source": cited[0] if cited else None,
                          "sources": cited, "by_agent": True, **v})
    questions.sort(key=lambda q: -q["gain"])

    actions = []
    for act in plan.get("actions", []):
        fx = _effects(act.get("effects", []), set(actors))
        texts = (act.get("title", ""), act.get("rationale", ""))
        if not fx or not texts[0] or any(_has_number(t) for t in texts):
            rejected.append({"kind": "action", "item": act, "reason": "sans effet, sans titre ou chiffre"})
            continue
        v = decision.action_value(data, base, fx, as_of)
        if v["gain"] <= 0:
            rejected.append({"kind": "action", "item": act, "reason": "aucun gain selon le modèle"})
            continue
        cited = [signals[i] for i in act.get("signal_ids", []) if i in signals]
        target = actors[next(iter(fx))]
        why = ("détenteur de veto · " if target["veto"] else "") + act.get("rationale", "")
        actions.append({"actor": target, "title": act["title"], "why": why, "effects": fx,
                        "source": cited[0] if cited else None, "sources": cited,
                        "by_agent": True, **v})
    actions.sort(key=lambda x: -x["gain"])
    return {"questions": questions[:MAX_QUESTIONS], "actions": actions[:MAX_ACTIONS],
            "rejected": rejected}


def run(conn, deal_id: str, as_of: str | None = None) -> dict:
    """Lance la boucle de l'agent (ou relit son résultat en cache) et renvoie le plan vérifié."""
    as_of = as_of or date.today().isoformat()
    data = model.load(conn, deal_id)
    base = model.posterior(data, as_of)
    messages = [{"role": "developer", "content": RULES},
                {"role": "user", "content": _state_message(conn, deal_id, data, base, as_of)}]

    key = hashlib.sha256(json.dumps([llm.model_name(), messages, TOOLS], ensure_ascii=False)
                         .encode()).hexdigest()[:16]
    cache = llm.CACHE_DIR / f"agent_{key}.json"
    if cache.exists():
        saved = json.loads(cache.read_text(encoding="utf-8"))
    else:
        tools = Tools(data, base, as_of)
        plan = None
        for step in range(MAX_STEPS):
            # au dernier tour, on impose submit_plan
            choice = ("auto" if step < MAX_STEPS - 1
                      else {"type": "function", "function": {"name": "submit_plan"}})
            msg = llm.chat_tools(messages, TOOLS, tool_choice=choice, **llm.effort("low"))
            messages.append(msg.model_dump(exclude_none=True))
            if not msg.tool_calls:
                messages.append({"role": "user", "content": "Use the tools, then call submit_plan."})
                continue
            for call in msg.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                if call.function.name == "submit_plan":
                    plan = args
                result = tools.run(call.function.name, args)
                messages.append({"role": "tool", "tool_call_id": call.id,
                                 "content": json.dumps(result, ensure_ascii=False)})
            if plan is not None:
                break
        saved = {"plan": plan or {"questions": [], "actions": []}, "trace": tools.trace,
                 "steps": step + 1}
        llm.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(saved, ensure_ascii=False, indent=2), encoding="utf-8")

    result = finalize(data, saved["plan"], as_of)
    result.update(trace=saved["trace"], steps=saved["steps"], proposed=saved["plan"])
    return result
