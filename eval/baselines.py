"""Références « Muse Spark seul » : on lui donne exactement ce que reçoit le copilote
(acteurs, rôles, veto, influence, débriefs) et on lui demande directement :
- la probabilité de signature (même consigne que le produit : copilot/forecast.py) ;
- les 2 acteurs sur lesquels il poserait une question au commercial.
"""

from __future__ import annotations

from copilot import llm
from copilot.forecast import deal_context, one_draw

PICK_SCHEMA = {
    "type": "object",
    "properties": {"actor_ids": {"type": "array", "items": {"type": "string"}},
                   "rationale": {"type": "string"}},
    "required": ["actor_ids", "rationale"], "additionalProperties": False,
}


def llm_probability(deal: dict, debriefs: list[tuple[str, str]], hypothesis: str | None = None,
                    cache_tag: str | None = None) -> float:
    """Un tirage de Muse Spark seul. hypothesis : phrase « et si ? » ajoutée (test de cohérence)."""
    return one_draw(deal, debriefs, hypothesis, cache_tag)["probability"]


def llm_pick_actors(deal: dict, debriefs: list[tuple[str, str]], n: int = 2) -> list[str]:
    rules = (f"You are an experienced sales director. Right after the last meeting you can ask the "
             f"sales rep about the position of {n} actors only. Which {n} actors would you ask about "
             f"to best predict whether the contract will be signed? Answer with their ids.")
    data = llm.chat_json([{"role": "developer", "content": rules},
                          {"role": "user", "content": deal_context(deal, debriefs)}],
                         name="pick", schema=PICK_SCHEMA, **llm.effort("low"))
    known = {a["id"] for a in deal["actors"]}
    return [i for i in data["actor_ids"] if i in known][:n]
