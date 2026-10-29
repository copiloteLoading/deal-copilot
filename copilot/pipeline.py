"""La chaîne complète, utilisée par l'interface (et plus tard par l'évaluation) :
débrief -> signaux -> mémoire -> modèle -> questions et actions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from copilot import agent, decision, extract, llm, memory, model

DEMO_DIR = Path(__file__).resolve().parent.parent / "data" / "demo_deal"
DEMO_ID = "port-aven-kerlis"
ANSWER_TITLE = "Réponse au débrief actif"


def setup_demo(conn, reset: bool = False) -> str:
    """Charge le contrat de démo et extrait les signaux des réunions passées (réponses en cache)."""
    known = conn.execute("SELECT 1 FROM deals WHERE id = ?", (DEMO_ID,)).fetchone()
    if reset or not known:
        memory.import_deal(conn, DEMO_DIR)
    for m in memory.meetings(conn, DEMO_ID):
        has_signals = conn.execute("SELECT 1 FROM signals WHERE meeting_id = ?", (m["id"],)).fetchone()
        if m["transcript"] and not has_signals:
            data = extract.extract(m["transcript"], conn, DEMO_ID)
            memory.add_signals(conn, DEMO_ID, m["id"], data["signals"])
            with conn:
                conn.execute("UPDATE meetings SET summary = ? WHERE id = ?", (data["summary"], m["id"]))
    return DEMO_ID


def analyze_debrief(conn, deal_id: str, text: str, day: str | None = None) -> dict:
    return extract.extract_and_store(conn, deal_id, day or date.today().isoformat(), text,
                                     "Débrief du jour")


def answer_question(conn, deal_id: str, question: dict, answer: str, day: str | None = None) -> dict | None:
    """Muse Spark lit la réponse à propos de l'acteur visé ; le signal obtenu passe par le modèle
    comme n'importe quel autre. Renvoie ce signal (None si rien d'exploitable)."""
    signal = extract.interpret_answer(question["text"], answer, question["actor"])
    meeting_id = memory.add_meeting(conn, deal_id, day or date.today().isoformat(), ANSWER_TITLE,
                                    f"Question : {question['text']}\nRéponse : {answer}")
    if signal:
        memory.add_signals(conn, deal_id, meeting_id, [signal])
    return signal


@dataclass
class DealState:
    deal: dict
    data: model.DealData
    post: model.Posterior
    last_contact: dict
    meetings: list[dict]
    timeline: list[tuple[str, model.Posterior]]   # (étiquette, probabilité après cette réunion)
    latest_debrief: dict | None                   # dernière réunion (hors réponses)
    latest_signals: list[dict]                    # signaux du dernier débrief et des réponses qui suivent
    moves: list[dict]                             # ce qui a fait bouger la probabilité


def state(conn, deal_id: str, as_of: str | None = None) -> DealState:
    as_of = as_of or date.today().isoformat()
    data = model.load(conn, deal_id)
    meetings = memory.meetings(conn, deal_id)
    all_signals = memory.signals(conn, deal_id)

    timeline = []
    for m in meetings:
        later = {s["id"] for s in all_signals if s["meeting_id"] > m["id"]}
        label = date.fromisoformat(m["date"]).strftime("%d/%m")
        if m["title"] == ANSWER_TITLE:
            label += " · réponse"
        timeline.append((label, model.posterior(data, m["date"], exclude=later)))

    debriefs = [m for m in meetings if m["title"] != ANSWER_TITLE]
    latest = debriefs[-1] if debriefs else None
    latest_ids = {m["id"] for m in meetings if latest and m["id"] >= latest["id"]}
    latest_signals = [s for s in all_signals if s["meeting_id"] in latest_ids]
    moves = model.explain(data, [s["id"] for s in latest_signals], as_of)

    return DealState(memory.get_deal(conn, deal_id), data, model.posterior(data, as_of),
                     memory.last_contact(conn, deal_id), meetings, timeline, latest,
                     latest_signals, moves)


def pending_changes(st: DealState, as_of: str | None = None) -> list[dict]:
    """Changements de position importants dus au dernier débrief et pas encore confirmés :
    un acteur qui passe de « pour » à « contre » (ou l'inverse), ou un veto qui bascule « contre ».
    Le modèle les compte déjà, mais le commercial doit les valider : une erreur d'extraction
    sur ces signaux-là changerait tout le plan."""
    as_of = as_of or date.today().isoformat()
    latest = {s["id"] for s in st.latest_signals}
    before = model.posterior(st.data, as_of, exclude=latest).beliefs
    out = []
    for a in st.data.actors:
        unconfirmed = [s for s in st.data.signals[a["id"]] if s["id"] in latest and not s.get("confirmed")]
        if not unconfirmed:
            continue
        was = model.STATES[int(before[a["id"]].argmax())]
        now = model.STATES[int(st.post.beliefs[a["id"]].argmax())]
        flip = {was, now} == {"support", "oppose"}
        veto_turns = a["veto"] and now == "oppose" and was != "oppose"
        if flip or veto_turns:
            out.append({"actor": a, "before": was, "after": now, "signals": unconfirmed})
    return out


def confirm_change(conn, change: dict, stance: str | None = None) -> None:
    """Le commercial valide le changement (stance=None), le corrige (stance donnée)
    ou le rejette (stance='unknown' : le signal ne compte plus pour le modèle)."""
    for s in change["signals"]:
        memory.confirm_signal(conn, s["id"], stance)


def plan(conn, deal_id: str) -> dict:
    """Questions et actions proposées par l'agent (Muse Spark + outils du modèle).
    En cas d'échec (pas de réseau, erreur d'API), on retombe sur les gabarits de decision.py."""
    try:
        result = agent.run(conn, deal_id)
        result["fallback"] = None
    except Exception as e:
        st = state(conn, deal_id)
        result = {"questions": decision.rank_questions(st.data, st.last_contact),
                  "actions": decision.rank_actions(st.data, st.last_contact),
                  "trace": [], "rejected": [], "steps": 0, "fallback": str(e)}
    return result


def refresh_actions(st: DealState, actions: list[dict]) -> list[dict]:
    """Rechiffre les actions déjà proposées avec l'état actuel (après une réponse, par exemple)."""
    out = []
    for act in actions:
        v = decision.action_value(st.data, st.post, act["effects"], date.today().isoformat())
        out.append({**act, **v})
    return sorted(out, key=lambda a: -a["gain"])


EMAIL_RULES = """You write a short, professional follow-up email in French for a sales rep.
Use only the facts given. Never invent a number, a date or a commitment. No probabilities.
Sign with the rep's name. Return only the email (subject line first, starting with "Objet :")."""


def followup_email(st: DealState, action: dict) -> str:
    """E-mail de suivi pour l'action n°1, rédigé par Muse Spark à partir des faits du dossier."""
    a = action["actor"]
    facts = [f"Rep: {st.deal['sales_rep']} ({st.deal['seller']})",
             f"Deal: {st.deal['name']}",
             f"Recipient: {a['name']}, {a['role']}",
             f"Goal of the email: {action['title']}"]
    if action.get("source"):
        facts.append(f"Context from the last debrief: « {action['source']['quote']} »")
    if st.latest_debrief and st.latest_debrief.get("summary"):
        facts.append(f"Summary of the last meeting: {st.latest_debrief['summary']}")
    return llm.chat([{"role": "developer", "content": EMAIL_RULES},
                     {"role": "user", "content": "\n".join(facts)}], **llm.effort("low"))


REMINDER_RULES = """You write a short message in French (5 to 8 lines) from a sales rep to a stakeholder
they have not talked to directly for a while, to re-establish contact and propose a short exchange.
Use only the facts given. Never invent a number, a date, a meeting or a commitment.
Never reveal the rep's internal analysis: no positions, no probabilities, no "you have been silent".
Courteous and concrete, adapted to the recipient's role. Sign with the rep's name.
Return only the message (subject line first, starting with "Objet :")."""


def reminder(st: DealState, actor: dict) -> str:
    """Message de reprise de contact pour un acteur silencieux, rédigé par Muse Spark."""
    org = next((o["name"] for o in st.deal["organizations"] if o["id"] == actor["org_id"]), "")
    last = st.last_contact.get(actor["id"])
    facts = [f"Rep: {st.deal['sales_rep']} ({st.deal['seller']})",
             f"Deal: {st.deal['name']} ({st.deal['description']})",
             f"Recipient: {actor['name']}, {actor['role']}, {org}",
             f"Last direct exchange: {last or 'none recorded'}"]
    known = st.data.signals[actor["id"]]
    if known:
        s = known[-1]
        facts.append(f"Last thing reported about them ({s['date']}): « {s['quote']} »")
    return llm.chat([{"role": "developer", "content": REMINDER_RULES},
                     {"role": "user", "content": "\n".join(facts)}], **llm.effort("low"))

