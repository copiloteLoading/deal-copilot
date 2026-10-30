"""Interface Streamlit de deal-copilot (V1 branchée sur la vraie chaîne).

Débrief (voix ou texte) -> signaux (Muse Spark) -> mémoire -> modèle par acteur
-> questions du débrief actif -> plan d'action et e-mail de suivi.

Lancer : .\\.venv\\Scripts\\python.exe -m streamlit run app.py
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from copilot import capture, llm, memory, model, orgchart, photo, pipeline, prepare

SILENCE_DAYS = 30
TRAP_TEXT = (pipeline.DEMO_DIR / "trap" / "debrief_piege.txt").read_text(encoding="utf-8")
TRAP_TRUTH_ANSWER = ("Le budget est voté en janvier, et d'après Julien, le câble n'est pas encore "
                     "dans l'enveloppe prévue.")

NAVY, INK, MUTED, GRID, WARN = "#1F4E79", "#1A202C", "#718096", "#E2E8F0", "#B7791F"
FONT = "Inter, sans-serif"
STANCE = {   # libellé, couleur
    "support": ("Pour", "#2F855A"),
    "conditional": ("Conditionnel", "#D69E2E"),
    "neutral": ("Neutre", "#718096"),
    "oppose": ("Contre", "#C53030"),
    "unknown": ("Inconnu", "#CBD5E0"),
}
STRENGTH = {"strong": "nette", "weak": "faible"}
ORG_TYPE_LABEL = {"buyer": "Client", "consortium_member": "Membre du consortium", "financier": "Financeur",
                  "regulator": "Régulateur", "subcontractor": "Sous-traitant", "competitor": "Concurrent",
                  "other": "Autre"}
SOURCE = {"direct": "directe", "reported": "rapportée", "impression": "impression"}

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
[class*="st-key-card_confirm"] {{ border-left: 4px solid {WARN}; }}
.dc-overline {{ font-size: 0.75rem; font-weight: 600; letter-spacing: 0.08em;
    text-transform: uppercase; color: {NAVY}; }}
.dc-title {{ font-size: 2rem; font-weight: 700; color: {INK}; margin: 0.15rem 0 0.2rem; }}
.dc-meta {{ color: {MUTED}; font-size: 0.92rem; }}
.dc-section {{ font-size: 1.02rem; font-weight: 600; color: {INK}; margin-bottom: 0.1rem; }}
.dc-delta {{ text-align: right; font-size: 0.95rem; color: {MUTED}; white-space: nowrap; }}
.dc-delta b {{ color: {INK}; font-size: 1.05rem; }}
.dc-brand {{ font-size: 1.15rem; font-weight: 700; letter-spacing: -0.01em; }}
.dc-node {{ padding: 0.22rem 0; font-size: 0.95rem; color: {INK}; white-space: nowrap; overflow: hidden;
    text-overflow: ellipsis; }}
.dc-branch {{ color: {MUTED}; font-family: monospace; }}
.dc-dot {{ display: inline-block; width: 0.7rem; height: 0.7rem; border-radius: 50%; margin: 0 0.45rem 0 0.1rem;
    vertical-align: middle; }}
.dc-role {{ color: {MUTED}; font-size: 0.86rem; margin-left: 0.3rem; }}
.dc-tag {{ font-size: 0.72rem; font-weight: 600; border-radius: 6px; padding: 0.05rem 0.4rem; margin-left: 0.4rem; }}
.dc-veto {{ background: #FDE8E8; color: #9B2C2C; }}
.dc-silent {{ background: #FEF3C7; color: {WARN}; }}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ utilitaires
def pct(x: float) -> str:
    return f"{x * 100:.0f} %"


def section(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"<div class='dc-section'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)


def days_since(day: str | None) -> int | None:
    return None if day is None else (date.today() - date.fromisoformat(day)).days


def stance_of(b) -> str:
    """Position la plus probable, ou 'unknown' si l'acteur reste très incertain."""
    return "unknown" if model.entropy(b) > 0.9 else model.STATES[int(b.argmax())]


def reset_session() -> None:
    for k in ["plan", "answers", "email", "transcript", "debrief_text", "reminders", "noisy", "prep", "photo_image", "photo_read", "photo_rows", "photo_done",
              "photo_notes"]:
        st.session_state.pop(k, None)


# ------------------------------------------------------------------ données
conn = memory.connect()
with st.spinner("Préparation du dossier de démonstration…"):
    deal_id = pipeline.setup_demo(conn)
S = pipeline.state(conn, deal_id)
actors = {a["id"]: a for a in S.data.actors}
orgs = {o["id"]: o for o in S.deal["organizations"]}
if "plan" not in st.session_state:
    with st.spinner("L'agent prépare ses questions et son plan d'action (Muse Spark + modèle)…"):
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
    posts = [p for _, p in S.timeline]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=labels, y=[p.high * 100 for p in posts], mode="lines",
                             line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=labels, y=[p.low * 100 for p in posts], mode="lines",
                             line=dict(width=0), fill="tonexty", fillcolor="rgba(31,78,121,0.12)",
                             hoverinfo="skip", name="Intervalle à 80 %"))
    fig.add_trace(go.Scatter(x=labels, y=[p.p * 100 for p in posts], mode="lines+markers",
                             line=dict(color=NAVY, width=2.5),
                             marker=dict(size=8, color="white", line=dict(color=NAVY, width=2)),
                             name="Probabilité de signature",
                             customdata=[[p.low * 100, p.high * 100] for p in posts],
                             hovertemplate="%{x}<br><b>%{y:.0f} %</b> (%{customdata[0]:.0f} – "
                                           "%{customdata[1]:.0f} %)<extra></extra>"))
    fig.add_hline(y=50, line=dict(color=GRID, dash="dot", width=1))
    base_layout(fig, 300)
    fig.update_layout(yaxis=dict(range=[0, 100], ticksuffix=" %", gridcolor=GRID, zeroline=False),
                      xaxis=dict(type="category", showgrid=False, linecolor=GRID),
                      legend=dict(orientation="h", y=-0.18, font=dict(size=11, color=MUTED)))
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
        label, color = STANCE[key] if key != "unknown" else ("Incertain", STANCE["unknown"][1])
        ids = [a for a in actor_pos if stance_of(S.post.beliefs[a]) == key]
        if not ids:
            continue
        texts, hovers = [], []
        for a in ids:
            act, b = actors[a], S.post.beliefs[a]
            d = days_since(S.last_contact.get(a))
            crowded = sum(1 for x in S.data.actors if x["org_id"] == act["org_id"]) > 3
            silence = ""
            if is_silent(a):
                never = "jamais vu" if crowded else "aucun échange direct"
                silence = (f"<br><span style='color:{WARN};font-size:10px'>"
                           f"{never if d is None else f'silence {d} j'}</span>")
            if a in pending_ids:
                silence += f"<br><span style='color:{WARN};font-size:10px'><b>à confirmer</b></span>"
            shown = f"{act['name'][0]}. {act['name'].split(' ', 1)[-1]}" if crowded else act["name"]
            texts.append(shown + silence)
            hovers.append(f"<b>{act['name']}</b><br>{act['role']}"
                          f"{'<br><b>Détenteur de veto</b>' if act['veto'] else ''}"
                          f"<br>Pour {b[0]:.0%} · Neutre {b[1]:.0%} · Contre {b[2]:.0%}"
                          f"<br>Influence : {act['influence']:.0%}")
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
    st.caption("Copilote confidentiel pour les contrats d'infrastructure")
    st.selectbox("Contrat", [S.deal["name"]])
    st.caption(f"Modèle : **{llm.provider()}** · {llm.model_name()}")
    if st.button("Réinitialiser la démo", icon=":material/restart_alt:", width="stretch"):
        pipeline.setup_demo(conn, reset=True)
        reset_session()
        st.rerun()

    st.divider()
    for label, value in [("CLIENT", S.deal["buyer"]), ("VALEUR", f"{S.deal['value_meur']:.0f} M€"),
                         ("SIGNATURE VISÉE", S.deal["target_signature"]),
                         ("CONCURRENCE", ", ".join(S.deal["competitors"]))]:
        st.caption(label)
        st.markdown(value)
    st.divider()
    st.caption("RÉUNIONS")
    for m in reversed(S.meetings):
        st.markdown(f"**{m['date']}**  \n{m['title']}")


# ------------------------------------------------------------------ en-tête
st.markdown(
    f"<div class='dc-overline'>{S.deal['seller']} · {S.deal['buyer']}</div>"
    f"<div class='dc-title'>{S.deal['name']}</div>"
    f"<div class='dc-meta'>{S.deal['description']}</div>", unsafe_allow_html=True)
st.write("")

prev = S.timeline[-2][1].p if len(S.timeline) > 1 else S.post.p
c1, c2, c3, c4 = st.columns(4)
c1.metric("Probabilité de signature", pct(S.post.p),
          f"{(S.post.p - prev) * 100:+.0f} depuis l'étape précédente ({pct(prev)})")
c2.metric("Intervalle d'incertitude (80 %)", f"{pct(S.post.low)} – {pct(S.post.high)}")
c3.metric("Veto le plus incertain", most_uncertain["name"] if most_uncertain else "—",
          most_uncertain["role"] if most_uncertain else None, delta_color="off", delta_arrow="off")
c4.metric("Acteurs silencieux", len(silent), f"plus de {SILENCE_DAYS} jours sans échange direct",
          delta_color="off", delta_arrow="off")
st.write("")

tab_deal, tab_photo, tab_people, tab_prep, tab_sources = st.tabs(
    [":material/dashboard: Dossier", ":material/photo_camera: Photos", ":material/account_tree: Organisations",
     ":material/event: Préparer une réunion", ":material/description: Sources"])

# ------------------------------------------------------------------ onglet Dossier
with tab_deal:
    if pending:
        with st.container(key="card_confirm"):
            section("À confirmer avant de continuer",
                    "Changements de position importants tirés du dernier débrief. Le modèle les compte "
                    "déjà ; une erreur de lecture ici changerait tout le plan.")
            for i, c in enumerate(pending):
                a = c["actor"]
                quotes = " · ".join(f"« {s['quote']} »" for s in c["signals"])
                st.markdown(f"**{a['name']}** ({a['role']}){' · **veto**' if a['veto'] else ''} passerait "
                            f"de **{STANCE[c['before']][0].lower()}** à **{STANCE[c['after']][0].lower()}** "
                            f"d'après : {quotes}")
                b1, b2, b3, b4 = st.columns([1.2, 1.2, 1.4, 1], vertical_alignment="bottom")
                if b1.button("Confirmer", key=f"conf_ok_{i}", type="primary", width="stretch",
                             icon=":material/check:"):
                    pipeline.confirm_change(conn, c)
                    st.rerun()
                fix = b3.selectbox("Corriger en", ["support", "neutral", "conditional", "oppose"],
                                   format_func=lambda s: STANCE[s][0], key=f"conf_fix_{i}")
                if b4.button("Corriger", key=f"conf_set_{i}", width="stretch"):
                    pipeline.confirm_change(conn, c, stance=fix)
                    st.session_state.pop("plan", None)   # positions changées : l'agent refait son plan
                    st.rerun()
                if b2.button("Rejeter", key=f"conf_no_{i}", width="stretch", icon=":material/close:",
                             help="Erreur de lecture : ces signaux ne comptent plus pour le modèle."):
                    pipeline.confirm_change(conn, c, stance="unknown")
                    st.session_state.pop("plan", None)
                    st.rerun()
        st.write("")

    left, right = st.columns([1, 1.4], gap="medium")

    with left:
        with st.container(key="card_debrief"):
            section("Débrief de réunion", "Environ 60 secondes de dictée après la réunion.")
            audio = st.audio_input("Enregistrement vocal", label_visibility="collapsed")
            uploaded = st.file_uploader(":material/upload_file: Ou déposer un fichier audio (WAV)",
                                        type=["wav"])
            with st.expander("Saisir le texte à la place", icon=":material/edit_note:"):
                if st.button("Charger le débrief de démonstration", icon=":material/science:"):
                    st.session_state.debrief_text = TRAP_TEXT
                text = st.text_area("Texte du débrief", key="debrief_text", height=160,
                                    label_visibility="collapsed",
                                    placeholder="Réunion avec le consortium ce matin…")
            if st.button("Analyser le débrief", type="primary", icon=":material/auto_awesome:",
                         width="stretch"):
                source = audio or uploaded
                try:
                    with st.status("Analyse du débrief…", expanded=True) as status:
                        if source is not None:
                            st.write("Transcription (Muse Voice Transcribe)…")
                            text = capture.transcribe(source.getvalue(), memory.keywords(conn, deal_id))
                            st.session_state.transcript = text
                            snr = capture.estimate_snr(capture.read_wav16k(source.getvalue()))
                            st.session_state.noisy = snr < capture.NOISY_BELOW_DB
                        if not (text or "").strip():
                            status.update(label="Aucun débrief à analyser", state="error")
                            st.stop()
                        st.write("Extraction des signaux (Muse Spark)…")
                        pipeline.analyze_debrief(conn, deal_id, text)
                        st.write("L'agent choisit ses questions et son plan (Muse Spark + modèle)…")
                        st.session_state.plan = pipeline.plan(conn, deal_id)
                        st.session_state.answers = {}
                        st.session_state.pop("email", None)
                        status.update(label="Débrief analysé", state="complete")
                    st.rerun()
                except Exception as e:   # l'appli doit rester debout en démo
                    st.error(f"Échec de l'analyse : {e}")
            if st.session_state.get("noisy"):
                st.warning("Enregistrement très bruité : relisez la transcription avant de vous y fier.",
                           icon=":material/hearing:")
            if st.session_state.get("transcript"):
                with st.expander("Transcription", icon=":material/record_voice_over:"):
                    st.write(st.session_state.transcript)

    with right:
        with st.container(key="card_signals"):
            when = S.latest_debrief["date"] if S.latest_debrief else "—"
            section("Signaux extraits", f"Dernier débrief ({when}) et réponses qui ont suivi · "
                                        "chaque citation est vérifiée mot pour mot.")
            st.dataframe(
                [{"Acteur": s["raw_name"], "Type": s["signal_type"],
                  "Position": STANCE.get(s["stance"], ("?",))[0],
                  "Force": STRENGTH.get(s.get("strength") or "", "—"),
                  "Origine": SOURCE.get(s.get("source_type") or "", "—"),
                  "Citation": s["quote"], "Confiance": s["confidence"]}
                 for s in S.latest_signals],
                hide_index=True, width="stretch", height=260,
                column_config={
                    "Citation": st.column_config.TextColumn(width="large"),
                    "Confiance": st.column_config.ProgressColumn(min_value=0, max_value=1,
                                                                 format="%.2f", width="small"),
                })

    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(key="card_proba"):
            section("Probabilité de signature",
                    "Recalculée à chaque réunion par le modèle (positions des acteurs + veto).")
            st.plotly_chart(probability_chart(), width="stretch", config={"displayModeBar": False})
            if S.moves:
                st.caption("Ce qui l'a fait bouger au dernier débrief :")
                for mv in S.moves[:3]:
                    st.markdown(f"<span style='color:{MUTED}'>{mv['delta'] * 100:+.1f} pts</span> · "
                                f"**{mv['signal']['raw_name']}** : « {mv['signal']['quote']} »",
                                unsafe_allow_html=True)
    with right:
        with st.container(key="card_map"):
            section("Parties prenantes",
                    "Couleur : position la plus probable · taille : influence · "
                    "contour épais : détenteur de veto · gris clair : encore incertain")
            st.plotly_chart(stakeholder_map(), width="stretch", config={"displayModeBar": False})

    left, right = st.columns(2, gap="medium")
    with left:
        with st.container(key="card_questions"):
            qs = PLAN["questions"]
            section("Débrief actif", "Proposées par l'agent, retenues et classées par le modèle selon "
                                     "la baisse d'incertitude qu'elles apportent (au plus 2).")
            if not qs:
                st.info("Aucune question utile : la suivante n'apporterait presque rien.")
            for i, q in enumerate(qs):
                a = q["actor"]
                with st.container(border=True):
                    st.markdown(f"**Question {i + 1} sur {len(qs)}**")
                    if a["veto"]:
                        st.badge(f"Détenteur de veto · {a['name']}", icon=":material/gavel:",
                                 color="red")
                    st.markdown(q["text"])
                    st.caption(f"Incertitude réduite d'environ {q['gain'] * 100:.1f} pts en moyenne "
                               f"· intervalle attendu après la réponse : {pct(q['expected_low'])} – "
                               f"{pct(q['expected_high'])}")
                    done = st.session_state.answers.get(i)
                    if done == "skipped":
                        st.caption("Question passée.")
                    elif done is not None:
                        if done.get("signal"):
                            sig = done["signal"]
                            st.success(f"Lecture de votre réponse : **{STANCE[sig['stance']][0]}** "
                                       f"({STRENGTH[sig['strength']]}) · « {sig['evidence_quote']} » "
                                       f"· {sig['description']}", icon=":material/check:")
                        else:
                            st.caption("Réponse enregistrée, sans information sur la position.")
                    else:
                        if a["id"] == "sophie_lenoir" and st.button(
                                "Réponse de démonstration", key=f"demo_{i}", icon=":material/science:"):
                            st.session_state[f"answer_{i}"] = TRAP_TRUTH_ANSWER
                        answer = st.text_input("Réponse", key=f"answer_{i}",
                                               label_visibility="collapsed",
                                               placeholder="Répondez en une phrase…")
                        b1, b2 = st.columns(2)
                        if b1.button("Envoyer", key=f"send_{i}", type="primary", width="stretch",
                                     disabled=not answer.strip()):
                            with st.spinner("Lecture de la réponse (Muse Spark)…"):
                                sig = pipeline.answer_question(conn, deal_id, q, answer)
                            st.session_state.answers[i] = {"signal": sig}
                            st.session_state.pop("email", None)
                            st.rerun()
                        if b2.button("Passer", key=f"skip_{i}", width="stretch"):
                            st.session_state.answers[i] = "skipped"
                            st.rerun()

    with right:
        with st.container(key="card_actions"):
            section("Plan d'action", "Actions proposées par l'agent, classées selon la probabilité "
                                     "de signature si elles aboutissent (simulée par le modèle).")
            acts = pipeline.refresh_actions(S, PLAN["actions"])
            for i, act in enumerate(acts):
                if i:
                    st.divider()
                a, b = st.columns([4.5, 2], vertical_alignment="center")
                a.markdown(f"**{i + 1}. {act['title']}**")
                a.caption(act["why"])
                b.markdown(f"<div class='dc-delta'>{pct(act['p_before'])} → "
                           f"<b>{pct(act['p_after'])}</b></div>", unsafe_allow_html=True)
            st.write("")
            if S.latest_debrief and S.latest_debrief.get("summary"):
                with st.expander("Compte rendu du dernier débrief", icon=":material/summarize:"):
                    st.write(S.latest_debrief["summary"])
            if acts:
                with st.expander(f"E-mail de suivi pour l'action n° 1", icon=":material/mail:"):
                    if st.button("Rédiger l'e-mail (Muse Spark)", icon=":material/edit:"):
                        with st.spinner("Rédaction…"):
                            st.session_state.email = pipeline.followup_email(S, acts[0])
                    if st.session_state.get("email"):
                        st.text_area("E-mail", st.session_state.email, height=260,
                                     label_visibility="collapsed")
            with st.expander(f"Acteurs silencieux ({len(silent)})", icon=":material/notifications:"):
                reminders = st.session_state.setdefault("reminders", {})
                for a in sorted(silent, key=lambda x: (not x["veto"], -x["influence"])):
                    d = days_since(S.last_contact.get(a["id"]))
                    when = "aucun échange direct enregistré" if d is None else f"silence depuis {d} jours"
                    c1, c2 = st.columns([4, 1.6], vertical_alignment="center")
                    c1.markdown(f"**{a['name']}** ({a['role']}, {orgs[a['org_id']]['name']})"
                                f"{' · veto' if a['veto'] else ''} · {when}")
                    if c2.button("Rédiger un rappel", key=f"remind_{a['id']}", icon=":material/edit:",
                                 width="stretch"):
                        with st.spinner("Rédaction (Muse Spark)…"):
                            reminders[a["id"]] = pipeline.reminder(S, a)
                    if a["id"] in reminders:
                        st.text_area("Rappel", reminders[a["id"]], height=200, key=f"remind_txt_{a['id']}",
                                     label_visibility="collapsed")

    with st.container(key="card_agent"):
        section("Raisonnement de l'agent",
                "Muse Spark propose et interroge le modèle par ses outils ; le modèle chiffre et "
                "tranche. Aucun chiffre ne vient du LLM.")
        if PLAN.get("fallback"):
            st.warning(f"Agent indisponible ({PLAN['fallback']}) : questions et actions issues des "
                       "gabarits du moteur de décision.", icon=":material/warning:")
        else:
            n_tools = sum(1 for c in PLAN["trace"] if c["tool"] != "submit_plan")
            st.caption(f"{PLAN['steps']} tours · {n_tools} appels d'outils · "
                       f"{len(PLAN['rejected'])} proposition(s) écartée(s) par le modèle")
            with st.expander("Voir chaque appel d'outil", icon=":material/account_tree:"):
                for c in PLAN["trace"]:
                    args, res = c["args"], c["result"]
                    name = actors.get(args.get("actor_id"), {}).get("name", args.get("actor_id"))
                    if "error" in res:
                        st.markdown(f"- `{c['tool']}` → erreur : {res['error']}")
                    elif c["tool"] == "get_signals":
                        st.markdown(f"- **Lit les signaux** de {name} ({len(res['signals'])})")
                    elif c["tool"] == "evaluate_question":
                        lo, hi = res["expected_interval_after_answer"]
                        st.markdown(f"- **Évalue une question** sur {name} : incertitude réduite de "
                                    f"{res['uncertainty_reduction_points']} pts (intervalle attendu "
                                    f"{lo} – {hi} %)")
                    elif c["tool"] == "simulate_action":
                        fx = ", ".join(f"{actors[e['actor_id']]['name']} → "
                                       f"{STANCE[e['stance']][0].lower()}"
                                       for e in args["effects"] if e["actor_id"] in actors)
                        st.markdown(f"- **Simule** « {fx} » : {res['probability_now_percent']} % → "
                                    f"{res['probability_if_success_percent']} %")
                    else:
                        st.markdown(f"- **Rend son plan** : {len(args.get('questions', []))} question(s), "
                                    f"{len(args.get('actions', []))} action(s)")
                for r in PLAN["rejected"]:
                    st.markdown(f"- ✕ Écarté ({r['kind']}) : {r['reason']}")

# ------------------------------------------------------------------ onglet Préparer une réunion
with tab_prep:
    st.caption("Avant une réunion : ce qu'il faut obtenir de chaque participant, quoi leur demander, "
               "et ce que la réunion peut faire basculer. Les chiffres viennent du modèle, les "
               "formulations de Muse Spark.")
    with st.container(key="card_prep_form"):
        c1, c2 = st.columns([2, 1])
        prep_title = c1.text_input("Réunion", "Comité de pilotage")
        prep_day = c2.date_input("Date", date.today() + timedelta(days=7), format="DD/MM/YYYY")
        who = st.multiselect(
            "Participants", list(actors),
            format_func=lambda a: f"{actors[a]['name']} · {actors[a]['role']} "
                                  f"({orgs[actors[a]['org_id']]['name']}){' · veto' if actors[a]['veto'] else ''}",
            placeholder="Qui sera présent ?")
        if st.button("Préparer la réunion", type="primary", icon=":material/event_note:",
                     disabled=not who):
            with st.spinner("Le modèle chiffre les enjeux, Muse Spark formule…"):
                st.session_state.prep = prepare.prepare(S.data, who, S.last_contact,
                                                        prep_day.isoformat(), prep_title)
    P = st.session_state.get("prep")
    if P:
        st.write("")
        if P["fallback"]:
            st.warning(f"Muse Spark indisponible ({P['fallback']}) : formulations par défaut.",
                       icon=":material/warning:")
        m1, m2, m3 = st.columns(3)
        m1.metric("Probabilité aujourd'hui", pct(P["p_now"]))
        m2.metric("Si la réunion se passe bien", pct(P["p_best"]),
                  f"{(P['p_best'] - P['p_now']) * 100:+.0f} · tous les participants favorables")
        m3.metric("Si l'enjeu principal se ferme", pct(P["p_worst"]),
                  f"{(P['p_worst'] - P['p_now']) * 100:+.0f} · "
                  f"{P['attendees'][0]['actor']['name']} défavorable")
        if P["opening"]:
            st.info(P["opening"], icon=":material/flag:")
        for i, r in enumerate(P["attendees"]):
            a, b = r["actor"], r["belief"]
            with st.container(key=f"card_prep_{i}"):
                left, right = st.columns([3, 1.2], vertical_alignment="top")
                with left:
                    st.markdown(f"**{i + 1}. {a['name']}** · {a['role']}, {orgs[a['org_id']]['name']}")
                    if a["veto"]:
                        st.badge("Détenteur de veto", icon=":material/gavel:", color="red")
                    silence = ("aucun échange direct" if r["silence"] is None
                               else f"dernier échange direct il y a {r['silence']} jours")
                    st.caption(f"Aujourd'hui : pour {b[0]:.0%} · neutre {b[1]:.0%} · contre {b[2]:.0%} · {silence}")
                    st.markdown(f":material/target: **Objectif** : {r['objective']}")
                    st.markdown(f":material/help: **À lui demander** : {r['question']}")
                    st.markdown(f":material/warning: **Attention** : {r['watch_out']}")
                    if r["sources"]:
                        st.caption("Sources : " + " · ".join(f"« {s['quote']} » ({s['date']})"
                                                              for s in r["sources"][:3]))
                with right:
                    st.markdown(f"<div class='dc-delta'>favorable<br><b>{pct(r['p_if_support'])}</b></div>",
                                unsafe_allow_html=True)
                    st.markdown(f"<div class='dc-delta'>défavorable<br><b>{pct(r['p_if_oppose'])}</b></div>",
                                unsafe_allow_html=True)
        if P["absent_vetoes"]:
            st.warning("Détenteurs de veto absents et mal connus, à aborder indirectement : "
                       + ", ".join(f"**{a['name']}** ({a['role']})" for a in P["absent_vetoes"]),
                       icon=":material/person_off:")

# ------------------------------------------------------------------ onglet Photos
SAMPLES = Path(__file__).resolve().parent / "samples"
SAMPLE_PHOTOS = {"Notes manuscrites (rendez-vous banque)": "notes_reunion_banque.jpg",
                 "Tableau blanc (atelier phasage)": "tableau_blanc_phasage.jpg",
                 "Organigramme (Baltis Telecom)": "organigramme_baltis.jpg"}


def reset_photo() -> None:
    for k in ["photo_read", "photo_rows", "photo_notes", "photo_done"]:
        st.session_state.pop(k, None)


with tab_photo:
    st.caption("Notes manuscrites, tableau blanc, organigramme : prenez-les en photo. Muse Spark les remet "
               "au propre, vous relisez, et le dossier se met à jour comme après un débrief dicté.")
    left, right = st.columns([1, 1.3], gap="medium")
    with left:
        with st.container(key="card_photo_in"):
            shot = st.file_uploader("Photo", type=["jpg", "jpeg", "png"], on_change=reset_photo)
            if shot is not None:
                st.session_state.photo_image = (shot.getvalue(), shot.type or "image/jpeg")
            c1, c2 = st.columns([2, 1], vertical_alignment="bottom")
            sample = c1.selectbox("Ou un exemple", list(SAMPLE_PHOTOS))
            if c2.button("Charger", icon=":material/science:", width="stretch"):
                st.session_state.photo_image = ((SAMPLES / SAMPLE_PHOTOS[sample]).read_bytes(), "image/jpeg")
                reset_photo()
            if st.session_state.get("photo_image"):
                st.image(st.session_state.photo_image[0], width="stretch")
                if st.button("Lire la photo (Muse Spark)", type="primary", icon=":material/document_scanner:",
                             width="stretch"):
                    with st.spinner("Lecture et mise au propre…"):
                        try:
                            got = photo.read(*st.session_state.photo_image, deal_name=S.deal["name"],
                                             known_names=[a["name"] for a in S.data.actors])
                            st.session_state.photo_read = got
                            st.session_state.photo_notes = got["clean_notes"]
                            st.session_state.photo_rows = orgchart.propose(conn, deal_id, got)
                        except Exception as e:
                            st.error(f"Lecture impossible : {e}")
    with right:
        got = st.session_state.get("photo_read")
        if not got:
            with st.container(key="card_photo_empty"):
                section("Données nettoyées")
                st.caption("Chargez une photo puis lancez la lecture.")
        else:
            with st.container(key="card_photo_notes"):
                section(f"{photo.KINDS[got['kind']]} · {got['title']}",
                        "Remis au propre par Muse Spark. Relisez et corrigez : c'est ce texte qui sera "
                        "analysé, et chaque citation devra s'y trouver mot pour mot.")
                if got["illegible"]:
                    st.warning("Passages illisibles : " + " · ".join(got["illegible"]), icon=":material/visibility_off:")
                notes = st.text_area("Notes", key="photo_notes", height=300, label_visibility="collapsed")
                c1, c2 = st.columns([1, 1.6], vertical_alignment="bottom")
                written = got["date"] if len(got["date"]) == 10 else date.today().isoformat()
                day = c1.date_input("Date", date.fromisoformat(written), format="DD/MM/YYYY", key="photo_day")
                done = st.session_state.get("photo_done")
                if c2.button("Notes ajoutées au dossier" if done else "Ajouter au dossier comme notes de réunion",
                             type="primary", icon=":material/check:" if done else ":material/note_add:",
                             width="stretch", disabled=done or not notes.strip() or got["kind"] == "org_chart"):
                    with st.spinner("Extraction des signaux (Muse Spark)…"):
                        res = pipeline.analyze_debrief(conn, deal_id, notes, day.isoformat(), f"Photo : {got['title']}")
                    st.session_state.pop("plan", None)
                    st.session_state.pop("prep", None)
                    st.session_state.photo_done = True        # on garde la photo pour enregistrer les personnes
                    st.toast(f"{len(res['signals'])} signal(s) ajouté(s) au dossier", icon=":material/check:")
                    st.rerun()
            rows = st.session_state.get("photo_rows") or []
            if rows:
                with st.container(key="card_photo_people"):
                    section("Personnes repérées", "Cochez les nouvelles personnes à ajouter. La hiérarchie lue "
                                                  "(« rattaché à ») est enregistrée ; le veto n'est jamais deviné.")
                    table = [{"Ajouter": r["add"], "Nom": r["name"], "Fonction": r["role"],
                              "Organisation": r["organization"], "Rattaché à": r["manager"],
                              "Influence": r["influence"], "Veto": r["veto"],
                              "Statut": "déjà dans le dossier" if r["known_as"] else "nouveau"} for r in rows]
                    edited = st.data_editor(
                        table, hide_index=True, width="stretch", key="photo_editor", disabled=["Nom", "Statut"],
                        column_config={"Influence": st.column_config.NumberColumn(
                            min_value=0.0, max_value=1.0, step=0.1, format="%.1f")})
                    n_new = sum(1 for r, e in zip(rows, edited) if e["Ajouter"] and not r["known_as"])
                    if st.button(f"Enregistrer ({n_new} nouvelle(s) personne(s) et la hiérarchie)",
                                 icon=":material/group_add:", width="stretch"):
                        chosen = [{**r, "add": e["Ajouter"], "role": e["Fonction"], "organization": e["Organisation"],
                                   "manager": e["Rattaché à"], "influence": float(e["Influence"]),
                                   "veto": bool(e["Veto"])} for r, e in zip(rows, edited)]
                        created = orgchart.apply(conn, deal_id, chosen)
                        st.session_state.photo_rows = None
                        st.session_state.pop("plan", None)
                        st.session_state.pop("prep", None)
                        st.toast(f"{len(created)} personne(s) ajoutée(s), hiérarchie enregistrée",
                                 icon=":material/check:")
                        st.rerun()

# ------------------------------------------------------------------ onglet Organisations
with tab_people:
    st.caption("La hiérarchie de chaque partie prenante : qui rapporte à qui, où sont les veto, "
               "qui est silencieux. Couleur : position la plus probable.")
    trees = memory.hierarchy(S.deal)
    shown_orgs = [o for o in orgs.values() if o["id"] in trees]
    cols = st.columns(2, gap="medium")
    for i, o in enumerate(shown_orgs):
        with cols[i % 2]:
            with st.container(key=f"card_tree_{o['id']}"):
                section(o["name"], ORG_TYPE_LABEL.get(o["type"], o["type"] or ""))
                lines = []
                for a, depth in trees[o["id"]]:
                    b = S.post.beliefs[a["id"]]
                    key = stance_of(b)
                    color = STANCE[key][1]
                    d = days_since(S.last_contact.get(a["id"]))
                    tags = ""
                    if a["veto"]:
                        tags += "<span class='dc-tag dc-veto'>veto</span>"
                    if is_silent(a["id"]):
                        tags += f"<span class='dc-tag dc-silent'>{'jamais vu' if d is None else f'silence {d} j'}</span>"
                    branch = "&nbsp;" * 6 * (depth - 1) + "└─&nbsp;" if depth else ""
                    lines.append(
                        f"<div class='dc-node'><span class='dc-branch'>{branch}</span>"
                        f"<span class='dc-dot' style='background:{color}'></span>"
                        f"<b>{a['name']}</b> <span class='dc-role'>{a['role'] or ''}</span>{tags}</div>")
                st.markdown("".join(lines), unsafe_allow_html=True)

    with st.expander("Modifier un rattachement", icon=":material/account_tree:"):
        c1, c2, c3 = st.columns([1.3, 1.3, 1], vertical_alignment="bottom")
        who = c1.selectbox("Personne", list(actors), format_func=lambda a: actors[a]["name"], key="h_who")
        same_org = [None] + [a for a in actors if a != who and actors[a]["org_id"] == actors[who]["org_id"]]
        boss = c2.selectbox("Rattachée à", same_org, key="h_boss",
                            format_func=lambda a: "— personne (sommet) —" if a is None else actors[a]["name"])
        if c3.button("Enregistrer", width="stretch", key="h_save"):
            try:
                memory.set_manager(conn, deal_id, who, boss)
                st.rerun()
            except ValueError as e:
                st.error(str(e))

# ------------------------------------------------------------------ onglet Sources
with tab_sources:
    st.caption("Les débriefs d'origine et leurs signaux : chaque chiffre et chaque affirmation y renvoie.")
    by_meeting: dict[int, list] = {}
    for s in memory.signals(conn, deal_id):
        by_meeting.setdefault(s["meeting_id"], []).append(s)
    for m in reversed(S.meetings):
        with st.expander(f"{m['date']} · {m['title']}", icon=":material/article:"):
            st.text(m["transcript"] or "")
            for s in by_meeting.get(m["id"], []):
                st.markdown(f"- **{s['raw_name']}** · {STANCE.get(s['stance'], ('?',))[0]} · "
                            f"« {s['quote']} »")
