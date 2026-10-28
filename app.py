"""Interface Streamlit de deal-copilot.

Squelette : la mise en page est complète, mais les chiffres viennent de copilot/mock.py
et les boutons ne sont pas encore branchés.

Lancer : .\\.venv\\Scripts\\python.exe -m streamlit run app.py
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import plotly.graph_objects as go
import streamlit as st

from copilot import llm, mock

DATA = Path(__file__).parent / "data"
SILENCE_DAYS = 30  # au-delà, un acteur est considéré comme silencieux

NAVY = "#1F4E79"
INK = "#1A202C"
MUTED = "#718096"
GRID = "#E2E8F0"
WARN = "#B7791F"
FONT = "Inter, sans-serif"

STANCES = {
    "support": ("Soutien", "#2F855A"),
    "neutral": ("Neutre", "#718096"),
    "oppose": ("Opposé", "#C53030"),
    "unknown": ("Inconnu", "#CBD5E0"),
}

st.set_page_config(page_title="deal-copilot", page_icon=":material/sailing:", layout="wide")

# Les cartes sont des st.container(key="card_…") : Streamlit leur donne la classe st-key-card_…
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
.dc-overline {{
    font-size: 0.75rem; font-weight: 600; letter-spacing: 0.08em; text-transform: uppercase;
    color: {NAVY};
}}
.dc-title {{ font-size: 2rem; font-weight: 700; color: {INK}; margin: 0.15rem 0 0.2rem; }}
.dc-meta {{ color: {MUTED}; font-size: 0.92rem; }}
.dc-section {{ font-size: 1.02rem; font-weight: 600; color: {INK}; margin-bottom: 0.1rem; }}
.dc-action-delta {{ text-align: right; font-size: 0.95rem; color: {MUTED}; white-space: nowrap; }}
.dc-action-delta b {{ color: {INK}; font-size: 1.05rem; }}
[class*="st-key-card_actions"] hr {{ margin: 0.5rem 0; }}
.dc-brand {{ font-size: 1.15rem; font-weight: 700; letter-spacing: -0.01em; }}
</style>
""", unsafe_allow_html=True)


# ------------------------------------------------------------------ données
@st.cache_data
def load_deal(folder: str) -> tuple[dict, dict]:
    path = DATA / folder
    deal = json.loads((path / "deal.json").read_text(encoding="utf-8"))
    unknowns = json.loads((path / "unknowns.json").read_text(encoding="utf-8"))
    return deal, unknowns


def days_since(day: str | None) -> int | None:
    return None if day is None else (date.today() - date.fromisoformat(day)).days


def pct(x: float) -> str:
    return f"{x * 100:.0f} %"


def section(title: str, subtitle: str | None = None) -> None:
    st.markdown(f"<div class='dc-section'>{title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.caption(subtitle)


def not_ready() -> None:
    st.toast("Pas encore branché : arrive dans les prochains jours.",
             icon=":material/construction:")


deal, unknowns = load_deal("demo_deal")
orgs = {o["id"]: o for o in deal["organizations"]}
actors = {a["id"]: a for a in deal["actors"]}
unknown_by_id = {u["id"]: u for u in unknowns["unknowns"]}
silent = [a for a in deal["actors"]
          if (days_since(a["last_contact"]) or 999) > SILENCE_DAYS]


# ------------------------------------------------------------------ graphiques
def base_layout(fig: go.Figure, height: int) -> go.Figure:
    fig.update_layout(height=height, margin=dict(l=8, r=8, t=8, b=8),
                      plot_bgcolor="white", paper_bgcolor="white",
                      font=dict(family=FONT, color=INK, size=12),
                      hoverlabel=dict(font_family=FONT, bgcolor="white"))
    return fig


def probability_chart() -> go.Figure:
    dates, p, low, high, why = zip(*mock.PROBA_HISTORY)
    fig = go.Figure()
    # bande d'incertitude : borne haute puis borne basse remplie jusqu'à la haute
    fig.add_trace(go.Scatter(x=dates, y=[h * 100 for h in high], mode="lines",
                             line=dict(width=0), hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=dates, y=[l * 100 for l in low], mode="lines",
                             line=dict(width=0), fill="tonexty",
                             fillcolor="rgba(31,78,121,0.12)", hoverinfo="skip",
                             name="Intervalle d'incertitude (80 %)"))
    fig.add_trace(go.Scatter(x=dates, y=[v * 100 for v in p], mode="lines+markers",
                             line=dict(color=NAVY, width=2.5),
                             marker=dict(size=7, color="white", line=dict(color=NAVY, width=2)),
                             customdata=why, name="Probabilité de signature",
                             hovertemplate="%{x}<br><b>%{y:.0f} %</b><br>%{customdata}<extra></extra>"))
    fig.add_hline(y=50, line=dict(color=GRID, dash="dot", width=1))
    base_layout(fig, 300)
    fig.update_layout(yaxis=dict(range=[0, 100], ticksuffix=" %", gridcolor=GRID, zeroline=False),
                      xaxis=dict(showgrid=False, linecolor=GRID),
                      legend=dict(orientation="h", y=-0.18, font=dict(size=11, color=MUTED)))
    return fig


def stakeholder_map() -> go.Figure:
    fig = go.Figure()
    # liens acteur -> organisation
    for aid, (x, y) in mock.MAP_ACTORS.items():
        ox, oy = mock.MAP_ORGS[actors[aid]["org"]]
        fig.add_trace(go.Scatter(x=[x, ox], y=[y, oy], mode="lines", hoverinfo="skip",
                                 line=dict(color=GRID, width=1.2), showlegend=False))
    # organisations
    ox, oy = zip(*mock.MAP_ORGS.values())
    fig.add_trace(go.Scatter(
        x=ox, y=oy, mode="markers+text", showlegend=False, hoverinfo="skip",
        marker=dict(symbol="square", size=9, color=INK),
        text=[f"<b>{label}</b>" for label in mock.MAP_ORG_LABELS.values()],
        textposition="top center", textfont=dict(size=11, color=INK)))
    # acteurs : couleur = position, taille = influence, contour gris = incertain
    for stance, (label, color) in STANCES.items():
        ids = [a for a in mock.MAP_ACTORS if actors[a]["stance"] == stance]
        if not ids:
            continue
        texts, hovers = [], []
        for a in ids:
            act = actors[a]
            d = days_since(act["last_contact"])
            silence = ""
            if d is None or d > SILENCE_DAYS:
                silence = (f"<br><span style='color:{WARN};font-size:10px'>"
                           f"{'jamais contacté' if d is None else f'silence {d} j'}</span>")
            texts.append(act["name"] + silence)
            hovers.append(f"<b>{act['name']}</b><br>{act['role']}, {orgs[act['org']]['name']}"
                          f"{'<br><b>Détenteur de veto</b>' if act['veto'] else ''}"
                          f"<br>Influence : {act['influence']:.0%}<br>Position : {label}"
                          f"<br>Dernier contact : {'jamais' if d is None else f'il y a {d} j'}")
        # contour épais et sombre pour les détenteurs de veto
        line_colors = [INK if actors[a]["veto"] else ("white" if stance != "unknown" else MUTED)
                       for a in ids]
        line_widths = [3.5 if actors[a]["veto"] else 1.5 for a in ids]
        fig.add_trace(go.Scatter(
            x=[mock.MAP_ACTORS[a][0] for a in ids], y=[mock.MAP_ACTORS[a][1] for a in ids],
            mode="markers+text", name=label, text=texts, textposition="bottom center",
            textfont=dict(size=11, color=INK), hovertext=hovers, hoverinfo="text",
            marker=dict(size=[16 + 26 * actors[a]["influence"] for a in ids], color=color,
                        line=dict(color=line_colors, width=line_widths))))
    base_layout(fig, 380)
    fig.update_layout(xaxis=dict(visible=False, range=[-3.2, 3.2]),
                      yaxis=dict(visible=False, range=[-2.7, 2.4]),
                      legend=dict(orientation="h", y=-0.02, font=dict(size=11, color=MUTED)))
    return fig


# ------------------------------------------------------------------ barre latérale
with st.sidebar:
    st.markdown("<div class='dc-brand'>deal-copilot</div>", unsafe_allow_html=True)
    st.caption("Copilote confidentiel pour les contrats d'infrastructure")

    st.selectbox("Contrat", [deal["name"]])
    providers = ["meta", "baseten", "offline"]
    st.radio("Modèle", providers, index=providers.index(llm.provider()), horizontal=True,
             disabled=True, help="Se choisit avec LLM_PROVIDER dans .env")
    st.toggle("Mode démo (réponses en cache)", value=True, on_change=not_ready)

    st.divider()
    st.caption("CLIENT")
    st.markdown(deal["buyer"])
    st.caption("VALEUR")
    st.markdown(f"{deal['value_meur']} M€")
    st.caption("SIGNATURE VISÉE")
    st.markdown(deal["target_signature"])
    st.caption("CONCURRENCE")
    st.markdown(", ".join(deal["competitors"]))

    st.divider()
    st.caption("RÉUNIONS")
    for m in reversed(deal["meetings"]):
        st.markdown(f"**{m['date']}**  \n{m['title']}")


# ------------------------------------------------------------------ en-tête
head, badge = st.columns([4, 1.2], vertical_alignment="top")
head.markdown(
    f"<div class='dc-overline'>{deal['seller']} · {deal['buyer']}</div>"
    f"<div class='dc-title'>{deal['name']}</div>"
    f"<div class='dc-meta'>{deal['description']}</div>",
    unsafe_allow_html=True)
with badge:
    st.badge("Maquette · données fictives", icon=":material/construction:", color="orange")

st.write("")
previous_p = mock.PROBA_HISTORY[-2][1]
c1, c2, c3, c4 = st.columns(4)
c1.metric("Probabilité de signature", pct(mock.CURRENT["p"]),
          f"{mock.CURRENT['delta_pts']:+d} (réunion précédente : {pct(previous_p)})")
c2.metric("Intervalle d'incertitude", f"{pct(mock.CURRENT['low'])} – {pct(mock.CURRENT['high'])}")
c3.metric("État probable du dossier", mock.CURRENT["state"])
c4.metric("Acteurs silencieux", len(silent), f"plus de {SILENCE_DAYS} jours sans contact",
          delta_color="off", delta_arrow="off")

st.write("")
tab_deal, tab_sources = st.tabs([":material/dashboard: Dossier",
                                 ":material/description: Sources"])

# ------------------------------------------------------------------ onglet Dossier
with tab_deal:
    left, right = st.columns([1, 1.4], gap="medium")

    with left:
        with st.container(key="card_debrief"):
            section("Débrief de réunion", "Environ 60 secondes de dictée après la réunion.")
            st.audio_input("Enregistrement vocal", label_visibility="collapsed")
            st.file_uploader(":material/upload_file: Ou déposer un fichier audio",
                             type=["wav", "m4a", "mp3"])
            with st.expander("Saisir le texte à la place", icon=":material/edit_note:"):
                st.text_area("Texte du débrief", height=100, label_visibility="collapsed",
                             placeholder="Réunion avec le consortium ce matin…")
            st.button("Analyser le débrief", type="primary", icon=":material/auto_awesome:",
                      on_click=not_ready, width="stretch")

    with right:
        with st.container(key="card_signals"):
            section("Signaux extraits",
                    "Débrief du 2026-10-27 · chaque citation est copiée mot pour mot.")
            st.dataframe(
                [{**s, "Position": STANCES[s["Position"]][0]} for s in mock.SIGNALS],
                hide_index=True, width="stretch", height=250,
                column_order=["Acteur", "Type", "Citation", "Position", "Confiance"],
                column_config={
                    "Acteur": st.column_config.TextColumn(width="medium"),
                    "Type": st.column_config.TextColumn(width="small"),
                    "Citation": st.column_config.TextColumn(width="large"),
                    "Position": st.column_config.TextColumn(width="small"),
                    "Confiance": st.column_config.ProgressColumn(
                        min_value=0, max_value=1, format="%.2f", width="small"),
                })

    left, right = st.columns(2, gap="medium")

    with left:
        with st.container(key="card_proba"):
            section("Probabilité de signature",
                    "Dernière variation : condition de phasage (Sophie Lenoir), "
                    "silence de la banque (Thomas Riou).")
            st.plotly_chart(probability_chart(), width="stretch",
                            config={"displayModeBar": False})

    with right:
        with st.container(key="card_map"):
            section("Parties prenantes",
                    "Couleur : position · taille : influence · contour épais : détenteur de veto "
                    "· gris clair : position inconnue")
            st.plotly_chart(stakeholder_map(), width="stretch",
                            config={"displayModeBar": False})

    left, right = st.columns(2, gap="medium")

    with left:
        with st.container(key="card_questions"):
            section("Débrief actif",
                    "Les questions qui réduisent le plus l'incertitude sur la signature.")
            p, low, high = mock.CURRENT["p"], mock.CURRENT["low"], mock.CURRENT["high"]
            for i, q in enumerate(mock.QUESTIONS, start=1):
                u = unknown_by_id[q["unknown"]]
                target = actors.get(u["actor"])
                # intervalle attendu après la réponse : resserré autour de p
                shrink = 1 - (q["gain_pts"] / 100) / (high - low)
                new_low, new_high = p - (p - low) * shrink, p + (high - p) * shrink
                with st.container(border=True):
                    st.markdown(f"**Question {i} sur {len(mock.QUESTIONS)}**")
                    if target and target["veto"]:
                        st.badge(f"Détenteur de veto · {target['name']}",
                                 icon=":material/gavel:", color="red")
                    st.markdown(u["question"])
                    st.caption(f"Intervalle attendu après la réponse : {pct(new_low)} – "
                               f"{pct(new_high)} (aujourd'hui {pct(low)} – {pct(high)}). "
                               f"{u['why_unknown']}")
                    a, b, c = st.columns([2.4, 1.3, 1.1], vertical_alignment="bottom")
                    a.text_input("Réponse", key=f"answer_{i}", label_visibility="collapsed",
                                 placeholder="Répondez en une phrase…")
                    b.button("Dicter", key=f"mic_{i}", icon=":material/mic:",
                             on_click=not_ready, width="stretch")
                    c.button("Passer", key=f"skip_{i}", on_click=not_ready, width="stretch")
            st.button("Envoyer les réponses", type="primary", on_click=not_ready,
                      width="stretch")

    with right:
        with st.container(key="card_actions"):
            section("Plan d'action",
                    "Classé selon la probabilité de signature si l'action aboutit "
                    "(simulée par le modèle).")
            p = mock.CURRENT["p"]
            for i, act in enumerate(mock.ACTIONS):
                if i:
                    st.divider()
                a, b, c = st.columns([4.5, 2, 0.4], vertical_alignment="center")
                a.markdown(f"**{act['action']}**")
                a.caption(f"{act['why']} · source : {act['source']}")
                b.markdown(f"<div class='dc-action-delta'>{pct(p)} → "
                           f"<b>{pct(p + act['effect_pts'] / 100)}</b></div>",
                           unsafe_allow_html=True)
                c.checkbox("Fait", key=f"done_{i}", label_visibility="collapsed")
            st.write("")
            with st.expander("Compte rendu de la réunion", icon=":material/summarize:"):
                st.markdown(mock.MEETING_SUMMARY.replace("\n", "  \n"))
                st.button("Copier le compte rendu", icon=":material/content_copy:",
                          on_click=not_ready)
            with st.expander("E-mail de suivi pour l'action n° 1 (brouillon)",
                             icon=":material/mail:"):
                st.text_area("E-mail", mock.EMAIL_DRAFT, height=260,
                             label_visibility="collapsed")
                st.button("Copier l'e-mail", icon=":material/content_copy:", on_click=not_ready)
            with st.expander(f"Rappels pour les acteurs silencieux ({len(silent)})",
                             icon=":material/notifications:"):
                for a in silent:
                    d = days_since(a["last_contact"])
                    when = "jamais contacté(e)" if d is None else f"silence depuis {d} jours"
                    st.markdown(f"- **{a['name']}** ({a['role']}, "
                                f"{orgs[a['org']]['name']}) · {when}")
                st.button("Créer les rappels", icon=":material/alarm_add:", on_click=not_ready)

# ------------------------------------------------------------------ onglet Sources
with tab_sources:
    st.caption("Les débriefs d'origine : chaque chiffre et chaque affirmation y renvoie.")
    for m in reversed(deal["meetings"]):
        with st.expander(f"{m['date']} · {m['title']}", icon=":material/article:"):
            st.text((DATA / "demo_deal" / m["debrief"]).read_text(encoding="utf-8"))
