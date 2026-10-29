"""Références « Muse Spark seul » : on lui donne exactement ce que reçoit le copilote
(acteurs, rôles, veto, influence, débriefs) et on lui demande directement :
- la probabilité de signature ;
- les 2 acteurs sur lesquels il poserait une question au commercial.
"""

from __future__ import annotations

from copilot import llm

PROBA_SCHEMA = {
    "type": "object",
    "properties": {"probability": {"type": "number"}, "rationale": {"type": "string"}},
    "required": ["probability", "rationale"], "additionalProperties": False,
}

PICK_SCHEMA = {
    "type": "object",
    "properties": {"actor_ids": {"type": "array", "items": {"type": "string"}},
                   "rationale": {"type": "string"}},
    "required": ["actor_ids", "rationale"], "additionalProperties": False,
}


def deal_context(deal: dict, debriefs: list[tuple[str, str]]) -> str:
    orgs = {o["id"]: o["name"] for o in deal["organizations"]}
    lines = [f"Deal: {deal['name']} · seller: {deal['seller']} · buyer: {deal['buyer']}",
             "Key actors (id | name | role | organization | veto | influence):"]
    lines += [f"- {a['id']} | {a['name']} | {a['role']} | {orgs.get(a['org_id'], '')} | "
              f"{'VETO' if a['veto'] else '-'} | {a['influence']:.2f}" for a in deal["actors"]]
    lines.append("\nDebriefs dictated by the sales rep, oldest first:")
    lines += [f"\n[{day}]\n{text}" for day, text in debriefs]
    return "\n".join(lines)


def llm_probability(deal: dict, debriefs: list[tuple[str, str]], hypothesis: str | None = None,
                    cache_tag: str | None = None) -> float:
    """hypothesis : phrase « et si ? » ajoutée après les débriefs (test de cohérence)."""
    rules = ("You are an experienced sales director. Estimate the probability (between 0 and 1) "
             "that this contract will be SIGNED, as opposed to lost or delayed for a long time. "
             "Veto holders must all agree for the contract to be signed. Be calibrated.")
    user = deal_context(deal, debriefs)
    if hypothesis:
        user += f"\n\nHypothesis (assume it is true): {hypothesis}"
    data = llm.chat_json([{"role": "developer", "content": rules},
                          {"role": "user", "content": user}],
                         name="forecast", schema=PROBA_SCHEMA, cache_tag=cache_tag,
                         **llm.effort("low"))
    return min(1.0, max(0.0, float(data["probability"])))


def llm_pick_actors(deal: dict, debriefs: list[tuple[str, str]], n: int = 2) -> list[str]:
    rules = (f"You are an experienced sales director. Right after the last meeting you can ask the "
             f"sales rep about the position of {n} actors only. Which {n} actors would you ask about "
             f"to best predict whether the contract will be signed? Answer with their ids.")
    data = llm.chat_json([{"role": "developer", "content": rules},
                          {"role": "user", "content": deal_context(deal, debriefs)}],
                         name="pick", schema=PICK_SCHEMA, **llm.effort("low"))
    known = {a["id"] for a in deal["actors"]}
    return [i for i in data["actor_ids"] if i in known][:n]
