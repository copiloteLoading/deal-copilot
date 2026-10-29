"""Client LLM unique de deal-copilot.

Fournisseurs (variable d'environnement LLM_PROVIDER) :
  meta     API Meta (muse-spark-1.3), clé MODEL_API_KEY
  baseten  Muse Spark Open (open weights) via Baseten, compatible OpenAI, clé BASETEN_API_KEY
  offline  aucun appel réseau : on ne répond qu'à partir du cache
Par défaut : meta si MODEL_API_KEY ressemble à une vraie clé, sinon offline.

Chaque réponse est mise en cache dans data/cache/ (clé = hash de la requête) :
un appel n'est jamais payé deux fois, et la démo peut rejouer sans réseau.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache"

PROVIDERS = {
    "meta": {
        "base_url": "https://api.meta.ai/v1",
        "key_env": "MODEL_API_KEY",
        "model": "muse-spark-1.3",
    },
    # À vérifier quand on passera à l'open weights (planning : lundi).
    "baseten": {
        "base_url": "https://inference.baseten.co/v1",
        "key_env": "BASETEN_API_KEY",
        "model": "meta-models/muse-spark-open-1026",
    },
}


class OfflineMiss(RuntimeError):
    """Mode hors ligne et la requête n'est pas dans le cache."""


def _has_real_key(env: str) -> bool:
    key = os.environ.get(env, "")
    return bool(key) and "xxxx" not in key


def provider() -> str:
    name = os.environ.get("LLM_PROVIDER")
    if name:
        return name
    return "meta" if _has_real_key("MODEL_API_KEY") else "offline"


def model_name() -> str:
    """Modèle utilisé. Hors ligne, on rejoue les réponses du modèle Meta par défaut."""
    name = provider()
    if name == "offline":
        return os.environ.get("OFFLINE_MODEL", PROVIDERS["meta"]["model"])
    return PROVIDERS[name]["model"]


def effort(level: str) -> dict:
    """Effort de raisonnement ("low", "medium", "high") à passer à chat() / chat_json().

    Réglable sur l'API Meta ; ailleurs on n'envoie rien. Hors ligne on garde le paramètre
    pour retrouver les réponses mises en cache avec l'API Meta.
    """
    return {"reasoning_effort": level} if provider() in ("meta", "offline") else {}


_client = None


def _get_client():
    global _client
    if _client is None:
        from openai import OpenAI  # import tardif : inutile en mode hors ligne

        conf = PROVIDERS[provider()]
        if not _has_real_key(conf["key_env"]):
            raise RuntimeError(f"{conf['key_env']} manquante ou fictive dans .env")
        _client = OpenAI(base_url=conf["base_url"], api_key=os.environ[conf["key_env"]])
    return _client


def _cache_path(request: dict) -> Path:
    raw = json.dumps(request, sort_keys=True, ensure_ascii=False)
    return CACHE_DIR / (hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16] + ".json")


def chat(messages: list[dict], response_format: dict | None = None, **params) -> str:
    """Envoie une conversation et renvoie le texte de la réponse (avec cache)."""
    request = {"model": model_name(), "messages": messages, **params}
    if response_format:
        request["response_format"] = response_format

    path = _cache_path(request)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["content"]
    if provider() == "offline":
        raise OfflineMiss(f"Pas de réponse en cache pour cette requête ({path.name}).")

    resp = _get_client().chat.completions.create(**request)
    content = resp.choices[0].message.content
    usage = resp.usage.model_dump() if resp.usage else None

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"request": request, "content": content, "usage": usage},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return content


def chat_json(messages: list[dict], name: str, schema: dict, **params) -> dict:
    """Comme chat(), mais avec une sortie structurée validée par un JSON schema."""
    response_format = {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}
    return json.loads(chat(messages, response_format=response_format, **params))
