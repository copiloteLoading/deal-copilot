"""Interface Streamlit de deal-copilot.

Un seul écran, dans l'ordre du problème : débrief (voix, texte ou photo) -> signaux (Muse Spark)
-> probabilité de signature (Muse Spark, moyenne de 3 tirages) et positions des acteurs (modèle)
-> au plus 2 questions -> plan d'action, compte rendu, e-mail de suivi.

Lancer : .\\.venv\\Scripts\\python.exe -m streamlit run app.py
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from copilot import capture, clock, llm, memory, model, orgchart, photo, pipeline

SILENCE_DAYS = 30
TRAP_TEXT = (pipeline.DEMO_DIR / "trap" / "debrief_piege.txt").read_text(encoding="utf-8")
TRAP_ANSWER = json.loads((pipeline.DEMO_DIR / "trap" / "truth.json").read_text(encoding="utf-8")
                         )["expected_agent_behavior"]["rep_answer"]
SAMPLES = Path(__file__).resolve().parent / "samples"
SAMPLE_PHOTOS = {"Handwritten notes (bank meeting)": "notes_bank_meeting.jpg",
                 "Whiteboard (phasing workshop)": "whiteboard_phasing.jpg"}

NAVY, INK, MUTED, GRID, WARN = "#1F4E79", "#1A202C", "#718096", "#E2E8F0", "#B7791F"
FONT = "Inter, sans-serif"
STANCE = {   # libellé, couleur
    "support": ("Supportive", "#2F855A"),
    "conditional": ("Conditional", "#D69E2E"),
    "neutral": ("Neutral", "#718096"),
    "oppose": ("Opposed", "#C53030"),
    "unknown": ("Unknown", "#CBD5E0"),
}
STRENGTH = {"strong": "clear", "weak": "faint"}
SOURCE = {"direct": "said directly", "reported": "reported", "impression": "impression"}

st.set_page_config(page_title="deal-copilot", page_icon=":material/sailing:", layout="wide")
st.markdown(f"""
<style>
.block-container {{ padding-top: 3.2rem; max-width: 1400px; }}
[class*="st-key-card"] {{
    background: #FFFFFF; border: 1px solid {GRID}; border-radius: 10px;
    padding: 1.1rem 1.2rem 1rem; box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}}
[data-testid="stMetric"] {{
    background: #FFFFFF; border: 1px solid {GRID}; border-radius: 10px;
    padding: 0.9rem 1.1rem; box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}}
[data-testid="stMetricLabel"] p {{
    font-size: 0.78rem; color: {MUTED}; text-transform: uppercase; letter-spacing: 0.04em;
}}
[data-testid="stMetricValue"] {{ font-weight: 600; font-size: 1.7rem; }}
[class*="st-key-card_actions"] hr {{ margin: 0.5rem 0; }}
[class*="st-key-card_confirm"], [class*="st-key-card_unknown"] {{ border-left: 4px solid {WARN}; }}
.dc-overline {{ font-size: 0.75rem; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: {NAVY}; }}
.dc-title {{ font-size: 2rem; font-weight: 700; color: {INK}; margin: 0.15rem 0 0.2rem; }}
.dc-meta {{ color: {MUTED}; font-size: 0.92rem; }}
.dc-section {{ font-size: 1.02rem; font-weight: 600; color: {INK}; margin-bottom: 0.1rem; }}
.dc-impact {{ text-align: right; font-size: 0.8rem; font-weight: 600; white-space: nowrap; }}
.dc-brand {{ font-size: 1.15rem; font-weight: 700; letter-spacing: -0.01em; }}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ utilitaires
def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def section(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"<div class='dc-section'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)


def days_since(day: str | None) -> int | None:
    return None if day is None else (clock.today() - date.fromisoformat(day)).days


def stance_of(b) -> str:
    """Position la plus probable, ou 'unknown' si l'acteur reste très incertain."""
    return "unknown" if model.entropy(b) > 0.9 else model.STATES[int(b.argmax())]


def level(gain: float, high: float, medium: float) -> tuple[str, str]:
    """Le modèle classe questions et actions ; on affiche un niveau, pas son chiffre interne
    (la probabilité affichée vient de Muse Spark, deux échelles ne doivent pas se contredire)."""
    if gain >= high:
        return "High impact", "#2F855A"
    if gain >= medium:
        return "Medium impact", "#B7791F"
    return "Low impact", MUTED


def reset_session() -> None:
    for k in ["plan", "answers", "email", "transcript", "debrief_text", "noisy", "photo_image",
              "photo_read", "photo_rows", "photo_notes", "ignored_names"]:
        st.session_state.pop(k, None)


MAX_ACTIONS = int(os.environ.get("DEAL_COPILOT_MAX_ACTIONS", "0"))   # 0 = sans limite (usage local)


def allow_action() -> bool:
    """Version en ligne : chaque visiteur a un nombre limité d'actions qui appellent Muse
    (les crédits sont partagés entre tous les visiteurs)."""
    if not MAX_ACTIONS:
        return True
    used = st.session_state.get("actions_used", 0)
    if used >= MAX_ACTIONS:
        st.warning(f"Limit reached for this visit ({MAX_ACTIONS} actions): Muse credits are shared between "
                   "all visitors. Reload the page to start again.", icon=":material/block:")
        return False
    st.session_state.actions_used = used + 1
    return True


def after_new_entry() -> None:
    """Un débrief, une réponse ou des notes ont été ajoutés : l'agent refera son plan."""
    for k in ["plan", "email"]:
        st.session_state.pop(k, None)


# ------------------------------------------------------------------ données
if os.environ.get("DEAL_COPILOT_DB") == "session":
    # version en ligne : chaque visiteur a sa propre base, en mémoire, le temps de sa session
    if "conn" not in st.session_state:
        st.session_state.conn = memory.connect(":memory:")
    conn = st.session_state.conn
else:
    conn = memory.connect()          # usage personnel : une base locale qui persiste
with st.spinner("Opening the deal…"):
    deal_id = pipeline.setup_demo(conn)
with st.spinner("Muse Spark is estimating the probability of signature…"):
    S = pipeline.state(conn, deal_id)
actors = {a["id"]: a for a in S.data.actors}
orgs = {o["id"]: o for o in S.deal["organizations"]}
if "plan" not in st.session_state:
    with st.spinner("The copilot is choosing its questions and its plan (Muse Spark + model)…"):
        st.session_state.plan = pipeline.plan(conn, deal_id)
    st.session_state.answers = {}
PLAN = st.session_state.plan


def is_silent(actor_id: str) -> bool:
    d = days_since(S.last_contact.get(actor_id))
    return d is None or d > SILENCE_DAYS


silent = [a for a in S.data.actors if is_silent(a["id"])]
pending = pipeline.pending_changes(S)
pending_ids = {c["actor"]["id"] for c in pending}
vetoes = [a for a in S.data.actors if a["veto"]]
most_uncertain = max(vetoes, key=lambda a: model.entropy(S.post.beliefs[a["id"]])) if vetoes else None


# ------------------------------------------------------------------ graphiques
def base_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=8),
                      plot_bgcolor="white", paper_bgcolor="white",
                      font=dict(family=FONT, color=INK, size=12),
                      hoverlabel=dict(font_family=FONT, bgcolor="white"))
    return fig


def probability_chart() -> go.Figure:
    labels = [label for label, _ in S.timeline]
    points = [f for _, f in S.timeline]
    fig = go.Figure(go.Scatter(
        x=labels, y=[f["p"] * 100 for f in points], mode="lines+markers",
        line=dict(color=NAVY, width=2.5), marker=dict(size=8, color="white", line=dict(color=NAVY, width=2)),
        customdata=[[", ".join(pct(d) for d in f["draws"])] for f in points],
        hovertemplate="%{x}<br><b>%{y:.0f}%</b> (draws: %{customdata[0]})<extra></extra>"))
    fig.add_hline(y=50, line=dict(color=GRID, dash="dot", width=1))
    base_layout(fig, 280)
    fig.update_layout(yaxis=dict(range=[0, 100], ticksuffix="%", gridcolor=GRID, zeroline=False),
                      xaxis=dict(type="category", showgrid=False, linecolor=GRID), showlegend=False)
    return fig


def layout_positions() -> tuple[dict, dict]:
    """Organisations sur deux rangées, acteurs sous leur organisation (3 par ligne au plus).
    Chaque organisation reçoit une largeur proportionnelle au nombre de ses membres."""
    client_side = [o for o in orgs.values() if o["type"] != "competitor"]
    top = [o for o in client_side if o["type"] in ("buyer", "consortium_member")]
    bottom = [o for o in client_side if o not in top]
    org_pos, actor_pos, y = {}, {}, 1.6
    for row in (top, bottom):
        if not row:
            continue
        members = {o["id"]: [a for a in S.data.actors if a["org_id"] == o["id"]] for o in row}
        cols = [max(1, min(3, len(members[o["id"]]))) for o in row]
        x0, depth = -3.3, 0
        for o, c in zip(row, cols):
            span = 6.6 * c / sum(cols)
            cx, x0 = x0 + span / 2, x0 + span
            org_pos[o["id"]] = (cx, y)
            ms = members[o["id"]]
            for j, a in enumerate(ms):
                line, k = divmod(j, 3)
                n = min(3, len(ms) - 3 * line)
                actor_pos[a["id"]] = (cx + min(1.1, span / c) * (k - (n - 1) / 2), y - 0.85 - 1.15 * line)
            depth = max(depth, (len(ms) - 1) // 3 if ms else 0)
        y -= 0.85 + 1.15 * depth + 1.35
    return org_pos, actor_pos


def short_org(name: str) -> str:
    """Coupe les noms longs sur deux lignes pour la carte."""
    if len(name) <= 16:
        return name
    words, half = name.split(), len(name) // 2
    cut = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - half))
    return " ".join(words[:cut]) + "<br>" + " ".join(words[cut:])


def stakeholder_map() -> go.Figure:
    org_pos, actor_pos = layout_positions()
    fig = go.Figure()
    for aid, (x, y) in actor_pos.items():
        ox, oy = org_pos[actors[aid]["org_id"]]
        fig.add_trace(go.Scatter(x=[x, ox], y=[y, oy], mode="lines", hoverinfo="skip",
                                 line=dict(color=GRID, width=1.2), showlegend=False))
    fig.add_trace(go.Scatter(
        x=[p[0] for p in org_pos.values()], y=[p[1] for p in org_pos.values()],
        mode="markers+text", showlegend=False, hoverinfo="skip",
        marker=dict(symbol="square", size=9, color=INK),
        text=[f"<b>{short_org(orgs[o]['name'])}</b>" for o in org_pos],
        textposition="top center", textfont=dict(size=11, color=INK)))
    for key in ["support", "neutral", "oppose", "unknown"]:
        label, color = STANCE[key] if key != "unknown" else ("Uncertain", STANCE["unknown"][1])
        ids = [a for a in actor_pos if stance_of(S.post.beliefs[a]) == key]
        if not ids:
            continue
        texts, hovers = [], []
        for a in ids:
            act, b = actors[a], S.post.beliefs[a]
            d = days_since(S.last_contact.get(a))
            crowded = sum(1 for x in S.data.actors if x["org_id"] == act["org_id"]) > 3
            note = ""
            if is_silent(a):
                note = (f"<br><span style='color:{WARN};font-size:10px'>"
                        f"{'never met' if d is None else f'silent {d} d'}</span>")
            if a in pending_ids:
                note += f"<br><span style='color:{WARN};font-size:10px'><b>to confirm</b></span>"
            shown = f"{act['name'][0]}. {act['name'].split(' ', 1)[-1]}" if crowded else act["name"]
            texts.append(shown + note)
            hovers.append(f"<b>{act['name']}</b><br>{act['role']}"
                          f"{'<br><b>Veto holder</b>' if act['veto'] else ''}"
                          f"<br>Supportive {b[0]:.0%} · Neutral {b[1]:.0%} · Opposed {b[2]:.0%}"
                          f"<br>Influence: {act['influence']:.0%}")
        fig.add_trace(go.Scatter(
            x=[actor_pos[a][0] for a in ids], y=[actor_pos[a][1] for a in ids],
            mode="markers+text", name=label, text=texts, textposition="bottom center",
            textfont=dict(size=11, color=INK), hovertext=hovers, hoverinfo="text",
            marker=dict(size=[16 + 26 * actors[a]["influence"] for a in ids], color=color,
                        line=dict(color=[INK if actors[a]["veto"] else "white" for a in ids],
                                  width=[3.5 if actors[a]["veto"] else 1.5 for a in ids]))))
    bottom = min([p[1] for p in actor_pos.values()] + [-1.5])
    base_layout(fig, int(380 + 75 * max(0, -1.6 - bottom)))
    fig.update_layout(xaxis=dict(visible=False, range=[-3.6, 3.6]),
                      yaxis=dict(visible=False, range=[bottom - 0.8, 2.4]),
                      legend=dict(orientation="h", y=-0.02, font=dict(size=11, color=MUTED)))
    return fig


# ------------------------------------------------------------------ barre latérale
with st.sidebar:
    st.markdown("<div class='dc-brand'>deal-copilot</div>", unsafe_allow_html=True)
    st.caption("The sales rep's private copilot for multi-year infrastructure deals")
    st.selectbox("Deal", [S.deal["name"]])
    st.caption(f"Muse Spark (`{llm.model_name()}`) · Muse Voice Transcribe · {llm.provider()}")
    if st.button("Back to the initial deal", icon=":material/restart_alt:", width="stretch"):
        pipeline.setup_demo(conn, reset=True)
        reset_session()
        st.rerun()

    st.divider()
    for label, value in [("CLIENT", S.deal["buyer"]), ("VALUE", f"€{S.deal['value_meur']:.0f}M"),
                         ("TARGET SIGNATURE", S.deal["target_signature"]),
                         ("COMPETITION", ", ".join(S.deal["competitors"]))]:
        st.caption(label)
        st.markdown(value)
    st.divider()
    st.caption("HISTORY")
    for m in reversed(S.meetings):
        st.markdown(f"**{m['date']}**  \n{m['title']}")


# ------------------------------------------------------------------ en-tête
st.markdown(
    f"<div class='dc-overline'>{S.deal['seller']} · {S.deal['buyer']}</div>"
    f"<div class='dc-title'>{S.deal['name']}</div>"
    f"<div class='dc-meta'>{S.deal['description']}</div>", unsafe_allow_html=True)
st.write("")

c1, c2, c3 = st.columns(3)
if S.forecast:
    prev = S.timeline[-2][1]["p"] if len(S.timeline) > 1 else S.forecast["p"]
    c1.metric("Probability of signature", pct(S.forecast["p"]),
              f"{(S.forecast['p'] - prev) * 100:+.0f} pts since the previous entry")
else:
    c1.metric("Probability of signature", "—", "Muse Spark unavailable", delta_color="off", delta_arrow="off")
c2.metric("Most uncertain veto holder", most_uncertain["name"] if most_uncertain else "—",
          most_uncertain["role"] if most_uncertain else None, delta_color="off", delta_arrow="off")
c3.metric("Silent stakeholders", len(silent), f"no direct exchange for {SILENCE_DAYS}+ days",
          delta_color="off", delta_arrow="off")
st.write("")

# ------------------------------------------------------------------ à confirmer
if pending:
    with st.container(key="card_confirm"):
        section("Please confirm",
                "Major position changes read in the last debrief. A reading error here would change "
                "the whole plan.")
        for i, c in enumerate(pending):
            a = c["actor"]
            quotes = " · ".join(f"“{s['quote']}”" for s in c["signals"])
            st.markdown(f"**{a['name']}** ({a['role']}){' · **veto**' if a['veto'] else ''} would move "
                        f"from **{STANCE[c['before']][0].lower()}** to **{STANCE[c['after']][0].lower()}** "
                        f"based on: {quotes}")
            b1, b2, b3, b4 = st.columns([1.2, 1.2, 1.4, 1], vertical_alignment="bottom")
            if b1.button("Confirm", key=f"conf_ok_{i}", type="primary", width="stretch",
                         icon=":material/check:"):
                pipeline.confirm_change(conn, c)
                st.rerun()
            if b2.button("Reject", key=f"conf_no_{i}", width="stretch", icon=":material/close:",
                         help="Reading error: these signals no longer count."):
                pipeline.confirm_change(conn, c, stance="unknown")
                st.session_state.pop("plan", None)
                st.rerun()
            fix = b3.selectbox("Correct to", ["support", "neutral", "conditional", "oppose"],
                               format_func=lambda s: STANCE[s][0], key=f"conf_fix_{i}")
            if b4.button("Correct", key=f"conf_set_{i}", width="stretch"):
                pipeline.confirm_change(conn, c, stance=fix)
                st.session_state.pop("plan", None)
                st.rerun()
    st.write("")

ignored = st.session_state.setdefault("ignored_names", set())
unknown = [u for u in memory.unresolved(conn, deal_id) if u["name"] not in ignored]
if unknown:
    with st.container(key="card_unknown"):
        section("Who is this?", "These names appear in your debriefs but are not linked to anyone yet: "
                                "their signals do not count until you say who they are.")
        NEW, SKIP = "__new__", "__skip__"
        for i, u in enumerate(unknown):
            st.markdown(f"**“{u['name']}”** ({u['date']}): “{u['quote']}”")
            c1, c2, c3 = st.columns([1.6, 1.4, 0.8], vertical_alignment="bottom")
            choice = c1.selectbox("This is", [*actors, NEW, SKIP], key=f"who_{i}",
                                  format_func=lambda a: {NEW: "A new person", SKIP: "Ignore this name"}.get(
                                      a, f"{actors[a]['name']} ({actors[a]['role']})" if a in actors else a))
            org = c2.selectbox("Organization", list(orgs), key=f"who_org_{i}", disabled=choice != NEW,
                               format_func=lambda o: orgs[o]["name"])
            if c3.button("Save", key=f"who_ok_{i}", width="stretch"):
                if choice == SKIP:
                    ignored.add(u["name"])
                else:
                    target = choice if choice != NEW else memory.add_actor(conn, deal_id, u["name"], org, None)
                    memory.link_alias(conn, deal_id, target, u["name"])   # ses signaux comptent désormais
                    st.session_state.pop("plan", None)
                st.rerun()
    st.write("")


# ------------------------------------------------------------------ débrief
def read_photo_input() -> None:
    """Débrief par photo : notes manuscrites ou tableau blanc, remis au propre par Muse Spark."""
    shot = st.file_uploader("Photo of your notes or a whiteboard", type=["jpg", "jpeg", "png"])
    if shot is not None and st.session_state.get("photo_name") != shot.name:
        st.session_state.photo_image, st.session_state.photo_name = (shot.getvalue(), shot.type), shot.name
        st.session_state.pop("photo_read", None)
    c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
    sample = c1.selectbox("Or an example", list(SAMPLE_PHOTOS))
    if c2.button("Load", icon=":material/science:", width="stretch"):
        st.session_state.photo_image = ((SAMPLES / SAMPLE_PHOTOS[sample]).read_bytes(), "image/jpeg")
        st.session_state.photo_name = sample
        st.session_state.pop("photo_read", None)
    if not st.session_state.get("photo_image"):
        return
    st.image(st.session_state.photo_image[0], width="stretch")
    if not st.session_state.get("photo_read"):
        if st.button("Read the photo (Muse Spark)", type="primary", icon=":material/document_scanner:",
                     width="stretch"):
            if not allow_action():
                st.stop()
            with st.spinner("Reading and cleaning up…"):
                try:
                    got = photo.read(*st.session_state.photo_image, deal_name=S.deal["name"],
                                     known_names=[a["name"] for a in S.data.actors])
                    st.session_state.photo_read = got
                    st.session_state.photo_notes = got["clean_notes"]
                    st.session_state.photo_rows = [r for r in orgchart.propose(conn, deal_id, got) if r["add"]]
                    st.rerun()
                except Exception as e:
                    st.error(f"Could not read the photo: {e}")
        return
    got = st.session_state.photo_read
    st.caption(f"{photo.KINDS[got['kind']]} · {got['title']} · cleaned up by Muse Spark. Review and correct: "
               "this is the text that will be analyzed, and every quote must appear in it word for word.")
    if got["illegible"]:
        st.warning("Illegible: " + " · ".join(got["illegible"]), icon=":material/visibility_off:")
    notes = st.text_area("Notes", key="photo_notes", height=260, label_visibility="collapsed")
    new_people = st.session_state.get("photo_rows") or []
    keep = []
    if new_people:
        st.caption("New people spotted on the photo (veto rights are never guessed):")
        for i, r in enumerate(new_people):
            org = r["organization"] or "organization unknown"
            if st.checkbox(f"Add **{r['name']}** · {r['role'] or 'role unknown'} · {org}", value=True,
                           key=f"newp_{i}"):
                keep.append(r)
    written = got["date"] if len(got["date"]) == 10 else clock.today().isoformat()
    day = st.date_input("Date of the notes", date.fromisoformat(written), key="photo_day")
    if st.button("Analyze these notes", type="primary", icon=":material/auto_awesome:", width="stretch",
                 disabled=not notes.strip()):
        if not allow_action():
            st.stop()
        with st.spinner("Adding the people and extracting the signals (Muse Spark)…"):
            orgchart.apply(conn, deal_id, keep)
            pipeline.analyze_debrief(conn, deal_id, notes, day.isoformat(), f"Photo: {got['title']}")
        for k in ["photo_image", "photo_read", "photo_rows", "photo_notes", "photo_name"]:
            st.session_state.pop(k, None)
        after_new_entry()
        st.rerun()


left, right = st.columns([1, 1.4], gap="medium")
with left:
    with st.container(key="card_debrief"):
        section("Debrief", "About 60 seconds after the meeting: dictate it, type it, or snap your notes.")
        t_voice, t_text, t_photo = st.tabs([":material/mic: Voice", ":material/edit_note: Text",
                                            ":material/photo_camera: Photo"])
        with t_voice:
            audio = st.audio_input("Voice recording", label_visibility="collapsed")
            uploaded = st.file_uploader("Or upload an audio file (WAV)", type=["wav"])
        with t_text:
            if st.button("Use an example debrief", icon=":material/science:"):
                st.session_state.debrief_text = TRAP_TEXT
            text = st.text_area("Debrief text", key="debrief_text", height=180, label_visibility="collapsed",
                                placeholder="Meeting with the consortium this morning…")
        with t_photo:
            read_photo_input()
        if st.button("Analyze the debrief", type="primary", icon=":material/auto_awesome:", width="stretch",
                     help="Voice recording or uploaded file first, otherwise the typed text."):
            if not allow_action():
                st.stop()
            source = audio or uploaded
            try:
                with st.status("Analyzing the debrief…", expanded=True) as status:
                    if source is not None:
                        st.write("Transcription (Muse Voice Transcribe, with the deal's names as keywords)…")
                        text = capture.transcribe(source.getvalue(), memory.keywords(conn, deal_id))
                        st.session_state.transcript = text
                        snr = capture.estimate_snr(capture.read_wav16k(source.getvalue()))
                        st.session_state.noisy = snr < capture.NOISY_BELOW_DB
                    if not (text or "").strip():
                        status.update(label="Nothing to analyze", state="error")
                        st.stop()
                    st.write("Signal extraction (Muse Spark, quotes checked word for word)…")
                    pipeline.analyze_debrief(conn, deal_id, text)
                    after_new_entry()
                    status.update(label="Debrief analyzed", state="complete")
                st.rerun()
            except Exception as e:   # l'appli doit rester debout si l'API échoue
                st.error(f"Analysis failed: {e}")
        if st.session_state.get("noisy"):
            st.warning("Very noisy recording: check the transcript before relying on it.", icon=":material/hearing:")
        if st.session_state.get("transcript"):
            with st.expander("Transcript", icon=":material/record_voice_over:"):
                st.write(st.session_state.transcript)

with right:
    with st.container(key="card_signals"):
        when = S.latest_debrief["date"] if S.latest_debrief else "—"
        section("Signals", f"Last debrief ({when}) and the answers that followed · every quote is checked "
                           "word for word against what you said.")
        st.dataframe(
            [{"Who": s["raw_name"], "Type": s["signal_type"], "Stance": STANCE.get(s["stance"], ("?",))[0],
              "Strength": STRENGTH.get(s.get("strength") or "", "—"),
              "Source": SOURCE.get(s.get("source_type") or "", "—"),
              "Quote": s["quote"], "Confidence": s["confidence"]}
             for s in S.latest_signals],
            hide_index=True, width="stretch", height=300,
            column_config={"Quote": st.column_config.TextColumn(width="large"),
                           "Confidence": st.column_config.ProgressColumn(min_value=0, max_value=1, format="%.2f",
                                                                         width="small")})

# ------------------------------------------------------------------ probabilité et acteurs
left, right = st.columns(2, gap="medium")
with left:
    with st.container(key="card_proba"):
        section("Probability of signature",
                "Muse Spark reads the whole file (debriefs, answers, notes) and estimates the probability; "
                "average of 3 independent draws, re-estimated after every entry.")
        if S.timeline:
            st.plotly_chart(probability_chart(), width="stretch", config={"displayModeBar": False})
        if S.forecast:
            st.markdown(f":material/lightbulb: {S.forecast['rationale']}")
with right:
    with st.container(key="card_map"):
        section("Stakeholders", "Each person's position, remembered across meetings by the model · size: "
                                "influence · thick outline: veto holder · light grey: still uncertain")
        st.plotly_chart(stakeholder_map(), width="stretch", config={"displayModeBar": False})

# ------------------------------------------------------------------ questions et plan
left, right = st.columns(2, gap="medium")
with left:
    with st.container(key="card_questions"):
        qs = PLAN["questions"]
        section("The copilot's questions", "At most 2, aimed at what you may not have seen: proposed by Muse "
                                           "Spark, kept and ranked by the model by how much the answer would "
                                           "clarify the deal.")
        if not qs:
            st.info("No useful question: the next one would add almost nothing.")
        for i, q in enumerate(qs):
            a = q["actor"]
            with st.container(border=True):
                head, imp = st.columns([4, 1.4], vertical_alignment="center")
                head.markdown(f"**Question {i + 1} of {len(qs)}**")
                label, color = level(q["gain"], 0.04, 0.015)
                imp.markdown(f"<div class='dc-impact' style='color:{color}'>{label}</div>", unsafe_allow_html=True)
                if a["veto"]:
                    st.badge(f"Veto holder · {a['name']}", icon=":material/gavel:", color="red")
                st.markdown(q["text"])
                done = st.session_state.answers.get(i)
                if done == "skipped":
                    st.caption("Skipped.")
                elif done is not None:
                    if done.get("signal"):
                        sig = done["signal"]
                        st.success(f"Your answer, as understood: **{STANCE[sig['stance']][0]}** "
                                   f"({STRENGTH[sig['strength']]}) · “{sig['evidence_quote']}” "
                                   f"· {sig['description']}", icon=":material/check:")
                    else:
                        st.caption("Answer saved, without information on the position.")
                else:
                    if a["id"] == "sophie_lenoir" and st.button("Example answer", key=f"demo_{i}",
                                                                icon=":material/science:"):
                        st.session_state[f"answer_{i}"] = TRAP_ANSWER
                    answer = st.text_input("Answer", key=f"answer_{i}", label_visibility="collapsed",
                                           placeholder="Answer in one sentence…")
                    b1, b2 = st.columns(2)
                    if b1.button("Send", key=f"send_{i}", type="primary", width="stretch",
                                 disabled=not answer.strip()):
                        if not allow_action():
                            st.stop()
                        with st.spinner("Reading your answer (Muse Spark)…"):
                            sig = pipeline.answer_question(conn, deal_id, q, answer)
                        st.session_state.answers[i] = {"signal": sig}
                        st.session_state.pop("email", None)
                        st.rerun()
                    if b2.button("Skip", key=f"skip_{i}", width="stretch"):
                        st.session_state.answers[i] = "skipped"
                        st.rerun()

with right:
    with st.container(key="card_actions"):
        section("Action plan", "Proposed by Muse Spark, including creative options; checked and ranked by the "
                               "model by their effect on the veto holders and the other stakeholders.")
        acts = pipeline.refresh_actions(S, PLAN["actions"])
        for i, act in enumerate(acts):
            if i:
                st.divider()
            a, b = st.columns([4.5, 1.5], vertical_alignment="center")
            a.markdown(f"**{i + 1}. {act['title']}**")
            a.caption(act["why"])
            label, color = level(act["gain"], 0.10, 0.04)
            b.markdown(f"<div class='dc-impact' style='color:{color}'>{label}</div>", unsafe_allow_html=True)
        st.write("")
        if S.latest_debrief and S.latest_debrief.get("summary"):
            with st.expander("Minutes of the last debrief", icon=":material/summarize:"):
                st.write(S.latest_debrief["summary"])
        if acts:
            with st.expander("Follow-up email for action #1", icon=":material/mail:"):
                if st.button("Draft the email (Muse Spark)", icon=":material/edit:"):
                    if not allow_action():
                        st.stop()
                    with st.spinner("Drafting…"):
                        st.session_state.email = pipeline.followup_email(S, acts[0])
                if st.session_state.get("email"):
                    st.text_area("Email", st.session_state.email, height=260, label_visibility="collapsed")
        if silent:
            st.caption("Silent: " + " · ".join(
                f"{a['name']}{' (veto)' if a['veto'] else ''}"
                for a in sorted(silent, key=lambda x: (not x["veto"], -x["influence"]))))

# ------------------------------------------------------------------ raisonnement de l'agent
with st.container(key="card_agent"):
    section("How the copilot reasoned",
            "Muse Spark proposes and queries the stakeholder model through tools; the model scores and "
            "decides. The language model never writes a figure.")
    if PLAN.get("fallback"):
        st.warning(f"Agent unavailable ({PLAN['fallback']}): questions and actions come from the decision "
                   "engine's templates.", icon=":material/warning:")
    else:
        n_tools = sum(1 for c in PLAN["trace"] if c["tool"] != "submit_plan")
        st.caption(f"{PLAN['steps']} rounds · {n_tools} tool calls · {len(PLAN['rejected'])} proposal(s) "
                   "rejected by the model")
        with st.expander("See every tool call", icon=":material/account_tree:"):
            for c in PLAN["trace"]:
                args, res = c["args"], c["result"]
                name = actors.get(args.get("actor_id"), {}).get("name", args.get("actor_id"))
                if "error" in res:
                    st.markdown(f"- `{c['tool']}` → error: {res['error']}")
                elif c["tool"] == "get_signals":
                    st.markdown(f"- **Reads the signals** about {name} ({len(res['signals'])})")
                elif c["tool"] == "evaluate_question":
                    lab = level(res["uncertainty_reduction_points"] / 100, 0.04, 0.015)[0].lower()
                    st.markdown(f"- **Evaluates a question** about {name}: {lab}")
                elif c["tool"] == "simulate_action":
                    fx = ", ".join(f"{actors[e['actor_id']]['name']} → {STANCE[e['stance']][0].lower()}"
                                   for e in args["effects"] if e["actor_id"] in actors)
                    gain = (res["probability_if_success_percent"] - res["probability_now_percent"]) / 100
                    st.markdown(f"- **Simulates** “{fx}”: {level(gain, 0.10, 0.04)[0].lower()}")
                else:
                    st.markdown(f"- **Submits its plan**: {len(args.get('questions', []))} question(s), "
                                f"{len(args.get('actions', []))} action(s)")
            for r in PLAN["rejected"]:
                st.markdown(f"- ✕ Rejected ({r['kind']}): {r['reason']}")
