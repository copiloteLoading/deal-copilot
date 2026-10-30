"""Date du jour du copilote.

DEAL_COPILOT_TODAY (AAAA-MM-JJ) fige la date. Sert à la démo en ligne et à la vidéo : le dossier de
démo est daté du 29 octobre 2026, et les réponses de Muse Spark mises en cache (dont le plan de
l'agent, qui dépend de la date) restent valables quel que soit le jour où un juge l'ouvre.
"""

from __future__ import annotations

import os
from datetime import date


def today() -> date:
    fixed = os.environ.get("DEAL_COPILOT_TODAY")
    return date.fromisoformat(fixed) if fixed else date.today()
