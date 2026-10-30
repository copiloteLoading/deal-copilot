"""Personnes lues sur une photo (organigramme, notes, tableau blanc) -> acteurs du dossier.

La lecture de l'image est faite par photo.read (vision de Muse Spark). Ici :
1. propose() rapproche chaque personne du dossier : déjà connue (nom ou alias) ou nouvelle, et
             suggère une influence selon le niveau hiérarchique. Le veto n'est jamais deviné.
2. apply()   ajoute au dossier les lignes que le commercial a validées, sans jamais écraser un acteur,
             et enregistre la hiérarchie lue (qui rapporte à qui).
"""

from __future__ import annotations

from copilot import memory

INFLUENCE_BY_LEVEL = {1: 0.8, 2: 0.6}      # au-delà ou inconnu : 0.4 ; simple suggestion, modifiable


def propose(conn, deal_id: str, chart: dict) -> list[dict]:
    """Une ligne par personne lue : connue ou nouvelle, organisation rattachée, influence suggérée."""
    types = {o["name"]: o["type"] for o in chart.get("organizations", [])}
    rows = []
    for p in chart.get("people", []):
        name = (p.get("name") or "").strip()
        if not name:
            continue
        actor_id, _ = memory.resolve(conn, deal_id, name)
        org_name = (p.get("organization") or "").strip()
        org_id = memory.resolve(conn, deal_id, org_name)[1] if org_name else None
        rows.append({"add": actor_id is None, "name": name, "role": p.get("role", ""),
                     "organization": org_name, "org_id": org_id,
                     "org_type": types.get(org_name, "other"), "manager": p.get("manager", ""),
                     "influence": INFLUENCE_BY_LEVEL.get(p.get("level"), 0.4), "veto": False,
                     "known_as": actor_id})
    return rows


def apply(conn, deal_id: str, rows: list[dict]) -> list[str]:
    """Ajoute les personnes cochées (et leurs organisations si besoin), puis la hiérarchie lue :
    chaque personne est rattachée à son supérieur s'il est dans le dossier. Un acteur déjà connu
    reçoit un supérieur seulement s'il n'en avait pas. Renvoie les ids créés."""
    created, new_orgs = [], {}
    for r in rows:
        if not r.get("add") or r.get("known_as"):
            continue
        org_id = r.get("org_id") or memory.resolve(conn, deal_id, r["organization"])[1]
        if org_id is None and r.get("organization"):
            org_id = new_orgs.get(r["organization"]) or memory.add_organization(
                conn, deal_id, r["organization"], r.get("org_type"))
            new_orgs[r["organization"]] = org_id
        last_name = r["name"].split()[-1]
        r["created_as"] = memory.add_actor(conn, deal_id, r["name"], org_id, r.get("role"),
                                           r.get("influence", 0.5), r.get("veto", False),
                                           aliases=[last_name] if last_name != r["name"] else [])
        created.append(r["created_as"])
    current = {a["id"]: a.get("manager_id") for a in memory.get_deal(conn, deal_id)["actors"]}
    for r in rows:
        actor_id = r.get("known_as") or r.get("created_as")
        boss = memory.resolve(conn, deal_id, r.get("manager") or "")[0]
        if actor_id and boss and boss != actor_id and not current.get(actor_id):
            try:
                memory.set_manager(conn, deal_id, actor_id, boss)
            except ValueError:
                pass                                   # boucle lue sur l'image : on l'ignore
    return created
