"""Prendre en photo : organigramme, notes manuscrites, tableau blanc (vision de Muse Spark).

Un seul appel lit l'image et rend des données propres :
- kind         ce que montre l'image (org_chart, meeting_notes, whiteboard, other) ;
- clean_notes  le contenu remis au propre et organisé en rubriques (participants, points clés,
               positions exprimées, décisions, actions et échéances), sans rien inventer ;
               les passages illisibles sont signalés [illisible] ;
- people / organizations  les personnes visibles, leur fonction et leur rattachement.

Le commercial relit et corrige. Ensuite :
- les notes passent par la même extraction qu'un débrief dicté (pipeline.analyze_debrief),
  avec des citations vérifiées mot pour mot dans le texte qu'il a validé ;
- les personnes passent par orgchart.propose / apply (connues ou nouvelles, hiérarchie).
"""

from __future__ import annotations

import base64
import io

from copilot import llm

KINDS = {"org_chart": "Org chart", "meeting_notes": "Meeting notes",
         "whiteboard": "Whiteboard", "other": "Other document"}
ORG_TYPES = ["buyer", "consortium_member", "financier", "regulator", "subcontractor", "competitor", "other"]

SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {"type": "string", "enum": list(KINDS)},
        "title": {"type": "string"},
        "date": {"type": "string"},
        "clean_notes": {"type": "string"},
        "illegible": {"type": "array", "items": {"type": "string"}},
        "organizations": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "type": {"type": "string", "enum": ORG_TYPES}},
            "required": ["name", "type"], "additionalProperties": False}},
        "people": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "role": {"type": "string"},
            "organization": {"type": "string"}, "manager": {"type": "string"},
            "level": {"type": "integer"}},
            "required": ["name", "role", "organization", "manager", "level"],
            "additionalProperties": False}},
    },
    "required": ["kind", "title", "date", "clean_notes", "illegible", "organizations", "people"],
    "additionalProperties": False,
}

RULES = """A sales rep negotiating a multi-year infrastructure contract photographed a document:
an organization chart, handwritten meeting notes, a whiteboard, or something else.
Turn it into clean data. Be faithful: never add a fact, a name, a number or a date that is not visible.
- kind: org_chart, meeting_notes, whiteboard or other.
- title: a short title in English; date: the date written on it as YYYY-MM-DD, or "" if none.
- clean_notes: the content rewritten cleanly in English, in plain text with short headed sections
  when they apply: "Participants", "Key points", "Positions expressed" (who said or thinks what;
  keep words that were written between quotes exactly as written), "Decisions", "Actions and deadlines".
  Expand obvious abbreviations only when unambiguous, fix spelling, keep every name exactly as written.
  Write [illegible] where something cannot be read. For an org chart, list who reports to whom.
- illegible: the passages you could not read.
- people: every person visible, with their job title, organization, manager ("" if not shown) and
  hierarchy level (1 = top, 0 if unknown). organizations: the organizations visible, with their most
  likely type for an infrastructure deal."""


MAX_SIDE = 1600          # px : assez pour lire une écriture manuscrite, et le coût d'une photo reste borné


def shrink(image: bytes) -> tuple[bytes, str]:
    """Une photo de téléphone fait souvent 4000 px : on la réduit et on la réencode en JPEG."""
    from PIL import Image, ImageOps

    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image))).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, "JPEG", quality=85)
    return out.getvalue(), "image/jpeg"


def read(image: bytes, mime: str = "image/jpeg", deal_name: str = "", known_names: list[str] | None = None) -> dict:
    """Lit une photo et renvoie les données nettoyées (voir SCHEMA). L'image va dans le message user."""
    try:
        image, mime = shrink(image)
    except Exception:            # format inattendu : on envoie l'image telle quelle
        pass
    url = f"data:{mime};base64,{base64.b64encode(image).decode()}"
    hint = f"Deal: {deal_name}."
    if known_names:   # aide à lire l'écriture manuscrite, comme les keywords de la transcription
        hint += " Names already known in this deal (spell them this way if you see them): " + ", ".join(known_names)
    content = [{"type": "text", "text": hint}, {"type": "image_url", "image_url": {"url": url}}]
    return llm.chat_json([{"role": "developer", "content": RULES}, {"role": "user", "content": content}],
                         name="photo_capture", schema=SCHEMA, **llm.effort("low"))
