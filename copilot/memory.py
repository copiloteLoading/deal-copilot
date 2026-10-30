"""Mémoire du copilote : une base SQLite par machine (le commercial garde ses données).

Tables :
  deals          un contrat
  organizations  entreprises, financeurs, régulateurs, concurrents d'un contrat
  actors         personnes clés, avec alias, influence et droit de veto
  meetings       réunions et texte de leur débrief
  signals        observations extraites d'un débrief, avec citation exacte et confiance
  positions      historique des positions estimées par le modèle (rempli par model.py)

Résolution d'entités volontairement simple : un nom extrait est rattaché à un acteur
s'il correspond à son nom ou à un de ses alias (sans tenir compte des accents ni de la casse).
Sinon le signal est gardé avec actor_id NULL, en attente de confirmation par le commercial.
"""

from __future__ import annotations

import json
import sqlite3
import unicodedata
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "deal_copilot.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS deals (
    id               TEXT PRIMARY KEY,
    name             TEXT NOT NULL,
    seller           TEXT,
    sales_rep        TEXT,
    buyer            TEXT,
    description      TEXT,
    value_meur       REAL,
    opened           TEXT,
    target_signature TEXT,
    competitors      TEXT DEFAULT '[]'          -- liste JSON
);

CREATE TABLE IF NOT EXISTS organizations (
    id      TEXT NOT NULL,
    deal_id TEXT NOT NULL REFERENCES deals(id),
    name    TEXT NOT NULL,
    type    TEXT,                               -- buyer, financier, regulator, competitor...
    aliases TEXT DEFAULT '[]',                  -- liste JSON
    PRIMARY KEY (deal_id, id)
);

CREATE TABLE IF NOT EXISTS actors (
    id             TEXT NOT NULL,
    deal_id        TEXT NOT NULL REFERENCES deals(id),
    org_id         TEXT,
    name           TEXT NOT NULL,
    role           TEXT,
    influence      REAL DEFAULT 0.5,            -- entre 0 et 1
    veto           INTEGER DEFAULT 0,           -- 1 = détenteur de veto
    decision_power TEXT,
    aliases        TEXT DEFAULT '[]',           -- liste JSON
    manager_id     TEXT,                        -- supérieur hiérarchique (id d'acteur) ou NULL
    PRIMARY KEY (deal_id, id)
);

CREATE TABLE IF NOT EXISTS meetings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id    TEXT NOT NULL REFERENCES deals(id),
    date       TEXT NOT NULL,                   -- AAAA-MM-JJ
    title      TEXT,
    transcript TEXT,
    summary    TEXT
);

CREATE TABLE IF NOT EXISTS signals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id       TEXT NOT NULL REFERENCES deals(id),
    meeting_id    INTEGER NOT NULL REFERENCES meetings(id),
    actor_id      TEXT,                         -- NULL si le nom n'a pas été résolu
    org_id        TEXT,
    raw_name      TEXT,                         -- nom tel qu'extrait du débrief
    signal_type   TEXT,
    stance        TEXT,                         -- support, neutral, oppose, unknown
    description   TEXT,
    quote         TEXT,                         -- citation exacte du débrief
    confidence    REAL,
    strength      TEXT,                         -- strong (déclaration nette) ou weak (indice)
    source_type   TEXT,                         -- direct (la personne l'a dit), reported, impression
    confirmed     INTEGER DEFAULT 0             -- 1 = confirmé par le commercial
);

CREATE TABLE IF NOT EXISTS positions (
    deal_id   TEXT NOT NULL,
    actor_id  TEXT NOT NULL,
    date      TEXT NOT NULL,
    p_support REAL, p_neutral REAL, p_oppose REAL,
    PRIMARY KEY (deal_id, actor_id, date)
);
"""


# ------------------------------------------------------------------ connexion
def connect(path: Path | str = DB_PATH) -> sqlite3.Connection:
    """Ouvre la base (":memory:" pour les tests) et crée les tables si besoin."""
    if path != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    # migration : colonnes ajoutées après la création des premières bases
    columns = {r["name"] for r in conn.execute("PRAGMA table_info(signals)")}
    for col in ("strength", "source_type"):
        if col not in columns:
            conn.execute(f"ALTER TABLE signals ADD COLUMN {col} TEXT")
    if "manager_id" not in {r["name"] for r in conn.execute("PRAGMA table_info(actors)")}:
        conn.execute("ALTER TABLE actors ADD COLUMN manager_id TEXT")
    return conn


def _normalize(text: str) -> str:
    """'Mme Sophie LENOIR' -> 'mme sophie lenoir', sans accents."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().replace("’", "'").split())


# ------------------------------------------------------------------ import
def import_deal(conn: sqlite3.Connection, folder: Path | str) -> str:
    """Charge un contrat décrit par deal.json (remplace la version précédente)."""
    folder = Path(folder)
    deal = json.loads((folder / "deal.json").read_text(encoding="utf-8"))
    deal_id = deal["deal_id"]

    with conn:
        for table in ("signals", "meetings", "positions", "actors", "organizations"):
            conn.execute(f"DELETE FROM {table} WHERE deal_id = ?", (deal_id,))
        conn.execute(
            "INSERT OR REPLACE INTO deals VALUES (?,?,?,?,?,?,?,?,?,?)",
            (deal_id, deal["name"], deal.get("seller"), deal.get("sales_rep"),
             deal.get("buyer"), deal.get("description"), deal.get("value_meur"),
             deal.get("opened"), deal.get("target_signature"),
             json.dumps(deal.get("competitors", []), ensure_ascii=False)))
        for o in deal["organizations"]:
            conn.execute(
                "INSERT INTO organizations VALUES (?,?,?,?,?)",
                (o["id"], deal_id, o["name"], o.get("type"),
                 json.dumps(o.get("aliases", []), ensure_ascii=False)))
        for a in deal["actors"]:
            conn.execute(
                "INSERT INTO actors (id, deal_id, org_id, name, role, influence, veto, decision_power,"
                " aliases, manager_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (a["id"], deal_id, a.get("org"), a["name"], a.get("role"),
                 a.get("influence", 0.5), int(a.get("veto", False)),
                 a.get("decision_power"), json.dumps(a.get("aliases", []), ensure_ascii=False),
                 a.get("manager")))
        for m in deal.get("meetings", []):
            transcript = (folder / m["debrief"]).read_text(encoding="utf-8") if m.get("debrief") else None
            add_meeting(conn, deal_id, m["date"], m.get("title"), transcript)
    return deal_id


# ------------------------------------------------------------------ lecture
def get_deal(conn: sqlite3.Connection, deal_id: str) -> dict:
    row = conn.execute("SELECT * FROM deals WHERE id = ?", (deal_id,)).fetchone()
    if row is None:
        raise KeyError(f"Contrat inconnu : {deal_id}")
    deal = dict(row)
    deal["competitors"] = json.loads(deal["competitors"])
    deal["organizations"] = [
        {**dict(r), "aliases": json.loads(r["aliases"])}
        for r in conn.execute("SELECT * FROM organizations WHERE deal_id = ?", (deal_id,))]
    deal["actors"] = [
        {**dict(r), "veto": bool(r["veto"]), "aliases": json.loads(r["aliases"])}
        for r in conn.execute("SELECT * FROM actors WHERE deal_id = ?", (deal_id,))]
    return deal


def meetings(conn: sqlite3.Connection, deal_id: str) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM meetings WHERE deal_id = ? ORDER BY date, id", (deal_id,))]


def signals(conn: sqlite3.Connection, deal_id: str, actor_id: str | None = None) -> list[dict]:
    """Signaux du contrat (ou d'un acteur), du plus ancien au plus récent, avec la date de réunion."""
    query = """SELECT s.*, m.date AS date FROM signals s JOIN meetings m ON m.id = s.meeting_id
               WHERE s.deal_id = ?"""
    params: list = [deal_id]
    if actor_id:
        query += " AND s.actor_id = ?"
        params.append(actor_id)
    return [dict(r) for r in conn.execute(query + " ORDER BY m.date, s.id", params)]


def last_contact(conn: sqlite3.Connection, deal_id: str) -> dict[str, str | None]:
    """Date du dernier échange direct avec chaque acteur (None si jamais).

    Seuls les signaux 'direct' comptent : être cité en son absence (« Thomas n'était pas là »)
    n'est pas un contact, et c'est justement ce silence que le modèle doit voir.
    """
    out = {a["id"]: None for a in get_deal(conn, deal_id)["actors"]}
    for r in conn.execute(
            """SELECT s.actor_id, MAX(m.date) AS d FROM signals s
               JOIN meetings m ON m.id = s.meeting_id
               WHERE s.deal_id = ? AND s.actor_id IS NOT NULL AND s.source_type = 'direct'
                 AND s.signal_type != 'deadline'
               GROUP BY s.actor_id""", (deal_id,)):
        out[r["actor_id"]] = r["d"]
    return out


# ------------------------------------------------------------------ résolution d'entités
def resolve(conn: sqlite3.Connection, deal_id: str, name: str) -> tuple[str | None, str | None]:
    """Rattache un nom extrait à (actor_id, org_id). Renvoie (None, None) si rien ne correspond."""
    key = _normalize(name)
    if not key:
        return None, None
    deal = get_deal(conn, deal_id)
    for a in deal["actors"]:
        if key in {_normalize(n) for n in [a["name"], *a["aliases"]]}:
            return a["id"], a["org_id"]
    for o in deal["organizations"]:
        if key in {_normalize(n) for n in [o["name"], *o["aliases"]]}:
            return None, o["id"]
    return None, None


def keywords(conn: sqlite3.Connection, deal_id: str) -> list[str]:
    """Noms propres du dossier, à passer à Muse Voice Transcribe pour mieux les transcrire."""
    deal = get_deal(conn, deal_id)
    words = [deal["name"], deal["seller"], deal["buyer"], *deal["competitors"]]
    for item in deal["actors"] + deal["organizations"]:
        words += [item["name"], *item["aliases"]]
    # on garde les noms propres (avec une majuscule), sans doublons, dans l'ordre
    seen, out = set(), []
    for w in words:
        if w and w[0].isupper() and w not in seen:
            seen.add(w)
            out.append(w)
    return out


# ------------------------------------------------------------------ écriture
def add_meeting(conn: sqlite3.Connection, deal_id: str, date: str, title: str | None = None,
                transcript: str | None = None, summary: str | None = None) -> int:
    with conn:
        cur = conn.execute(
            "INSERT INTO meetings (deal_id, date, title, transcript, summary) VALUES (?,?,?,?,?)",
            (deal_id, date, title, transcript, summary))
    return cur.lastrowid


def add_signals(conn: sqlite3.Connection, deal_id: str, meeting_id: int,
                extracted: list[dict]) -> list[dict]:
    """Enregistre les signaux sortis de l'extraction et renvoie ceux qui n'ont pas été résolus."""
    unresolved = []
    with conn:
        for s in extracted:
            actor_id, org_id = resolve(conn, deal_id, s.get("actor_name", ""))
            if org_id is None and s.get("organization"):
                org_id = resolve(conn, deal_id, s["organization"])[1]
            conn.execute(
                """INSERT INTO signals (deal_id, meeting_id, actor_id, org_id, raw_name,
                   signal_type, stance, description, quote, confidence, strength, source_type)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (deal_id, meeting_id, actor_id, org_id, s.get("actor_name"),
                 s.get("signal_type"), s.get("stance"), s.get("description"),
                 s.get("evidence_quote"), s.get("confidence"), s.get("strength"),
                 s.get("source_type")))
            if actor_id is None and org_id is None:
                unresolved.append(s)
    return unresolved


def _new_id(conn: sqlite3.Connection, table: str, deal_id: str, name: str) -> str:
    base = "_".join(_normalize(name).replace("'", " ").replace("-", " ").split())[:40] or "item"
    new, n = base, 2
    while conn.execute(f"SELECT 1 FROM {table} WHERE deal_id = ? AND id = ?", (deal_id, new)).fetchone():
        new, n = f"{base}_{n}", n + 1
    return new


def add_organization(conn: sqlite3.Connection, deal_id: str, name: str, org_type: str | None = None,
                     aliases: list[str] | None = None) -> str:
    """Ajoute une organisation (lue sur un organigramme, par exemple) et renvoie son id."""
    org_id = _new_id(conn, "organizations", deal_id, name)
    with conn:
        conn.execute("INSERT INTO organizations VALUES (?,?,?,?,?)",
                     (org_id, deal_id, name, org_type, json.dumps(aliases or [], ensure_ascii=False)))
    return org_id


def add_actor(conn: sqlite3.Connection, deal_id: str, name: str, org_id: str | None, role: str | None,
              influence: float = 0.5, veto: bool = False, aliases: list[str] | None = None,
              manager_id: str | None = None) -> str:
    """Ajoute un acteur au dossier et renvoie son id (jamais d'écrasement d'un acteur existant)."""
    actor_id = _new_id(conn, "actors", deal_id, name)
    with conn:
        conn.execute("INSERT INTO actors (id, deal_id, org_id, name, role, influence, veto, decision_power,"
                     " aliases, manager_id) VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (actor_id, deal_id, org_id, name, role, float(influence), int(bool(veto)), None,
                      json.dumps(aliases or [], ensure_ascii=False), manager_id))
    return actor_id


def set_manager(conn: sqlite3.Connection, deal_id: str, actor_id: str, manager_id: str | None) -> None:
    """Rattache un acteur à son supérieur (None pour le détacher). Refuse les boucles."""
    seen, cur = {actor_id}, manager_id
    while cur:
        if cur in seen:
            raise ValueError("Ce rattachement créerait une boucle dans la hiérarchie.")
        seen.add(cur)
        row = conn.execute("SELECT manager_id FROM actors WHERE deal_id = ? AND id = ?",
                           (deal_id, cur)).fetchone()
        cur = row["manager_id"] if row else None
    with conn:
        conn.execute("UPDATE actors SET manager_id = ? WHERE deal_id = ? AND id = ?",
                     (manager_id, deal_id, actor_id))


def hierarchy(deal: dict) -> dict[str, list[tuple[dict, int]]]:
    """Arbre de chaque organisation : liste (acteur, profondeur) dans l'ordre d'affichage.
    Un acteur dont le supérieur est inconnu ou dans une autre organisation est une racine."""
    actors = {a["id"]: a for a in deal["actors"]}
    children: dict[str | None, list[dict]] = {}
    for a in deal["actors"]:
        boss = a.get("manager_id")
        root = boss not in actors or actors[boss]["org_id"] != a["org_id"]
        children.setdefault(None if root else boss, []).append(a)
    out: dict[str, list[tuple[dict, int]]] = {}

    def walk(a: dict, depth: int) -> None:
        out.setdefault(a["org_id"], []).append((a, depth))
        for c in sorted(children.get(a["id"], []), key=lambda x: (not x["veto"], -x["influence"])):
            walk(c, depth + 1)

    for a in sorted(children.get(None, []), key=lambda x: (not x["veto"], -x["influence"])):
        walk(a, 0)
    return out


def link_alias(conn: sqlite3.Connection, deal_id: str, actor_id: str, alias: str) -> None:
    """Le commercial confirme qu'un nom inconnu désigne un acteur : on retient l'alias
    et on rattache les signaux en attente qui portaient ce nom."""
    row = conn.execute("SELECT aliases FROM actors WHERE deal_id = ? AND id = ?",
                       (deal_id, actor_id)).fetchone()
    aliases = json.loads(row["aliases"])
    if alias not in aliases:
        aliases.append(alias)
    org_id = conn.execute("SELECT org_id FROM actors WHERE deal_id = ? AND id = ?",
                          (deal_id, actor_id)).fetchone()["org_id"]
    with conn:
        conn.execute("UPDATE actors SET aliases = ? WHERE deal_id = ? AND id = ?",
                     (json.dumps(aliases, ensure_ascii=False), deal_id, actor_id))
        for s in conn.execute("SELECT id, raw_name FROM signals WHERE deal_id = ? AND actor_id IS NULL",
                              (deal_id,)).fetchall():
            if _normalize(s["raw_name"]) == _normalize(alias):
                conn.execute("UPDATE signals SET actor_id = ?, org_id = ?, confirmed = 1 WHERE id = ?",
                             (actor_id, org_id, s["id"]))


def confirm_signal(conn: sqlite3.Connection, signal_id: int, stance: str | None = None) -> None:
    """Le commercial valide un signal (et peut corriger la position)."""
    with conn:
        if stance:
            conn.execute("UPDATE signals SET stance = ?, confirmed = 1 WHERE id = ?",
                         (stance, signal_id))
        else:
            conn.execute("UPDATE signals SET confirmed = 1 WHERE id = ?", (signal_id,))
