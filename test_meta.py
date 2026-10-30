"""Day 1 smoke tests for the Meta Model API (built during the Meta Global AI Developer Hackathon).

Usage:
    python test_meta.py ping
    python test_meta.py transcribe samples/debrief.wav [--lang french]
    python test_meta.py extract samples/debrief_example.txt
    python test_meta.py image samples/organigramme.jpg
    python test_meta.py all samples/debrief.wav samples/organigramme.jpg

Every result is saved in outputs/ so you never pay twice for the same call.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

API_KEY = os.environ.get("MODEL_API_KEY")
BASE_URL = "https://api.meta.ai/v1"
TRANSCRIBE_URL = "https://api.meta.ai/v1/asr/transcribe"
CHAT_MODEL = "muse-spark-1.3"
VOICE_MODEL = "muse-voice-transcribe-1.0"
OUT = Path("outputs")
OUT.mkdir(exist_ok=True)

if not API_KEY:
    sys.exit("MODEL_API_KEY manquante : crée un fichier .env (voir .env.example).")

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)


def show_usage(resp) -> None:
    u = resp.usage
    if u:
        print(f"   [tokens] entrée={u.prompt_tokens} sortie={u.completion_tokens}")


# ---------------------------------------------------------------- 1. ping
def ping() -> None:
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{"role": "user", "content": "Reply with the single word: ready"}],
    )
    print("Muse Spark :", resp.choices[0].message.content)
    show_usage(resp)


# ---------------------------------------------------------------- 2. voix
def transcribe(path: str, lang: str | None = None) -> str:
    """Mono 16-bit WAV at 16 or 24 kHz, max 10 minutes / 32 MB."""
    request = {"mode": "PUSH_TO_TALK", "model": VOICE_MODEL, "audioEncoding": "WAV"}
    if lang:
        request["languageBias"] = [lang]
    with open(path, "rb") as audio:
        r = requests.post(
            TRANSCRIBE_URL,
            headers={"Authorization": f"Bearer {API_KEY}"},
            files={
                "request": (None, json.dumps(request), "application/json"),
                "audio": (os.path.basename(path), audio),
            },
            timeout=300,
        )
    if r.status_code != 200:
        sys.exit(f"Erreur transcription {r.status_code} : {r.text[:300]}")
    result = r.json()
    text = result.get("transcript", "")
    print(f"Transcription ({(result.get('audioDurationMs') or 0) / 1000:.1f} s d'audio) :\n{text}")
    (OUT / (Path(path).stem + "_transcript.txt")).write_text(text, encoding="utf-8")
    return text


# ---------------------------------------------------------------- 3. signaux
SIGNALS_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "deal_signals",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string"},
                "signals": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "actor_name": {"type": "string"},
                            "organization": {"type": "string"},
                            "role": {"type": "string"},
                            "signal_type": {
                                "type": "string",
                                "enum": ["support", "objection", "commitment", "risk",
                                         "deadline", "competitor", "budget", "information"],
                            },
                            "stance": {"type": "string",
                                       "enum": ["support", "neutral", "oppose", "unknown"]},
                            "influence": {"type": "string",
                                          "enum": ["low", "medium", "high", "unknown"]},
                            "description": {"type": "string"},
                            "evidence_quote": {"type": "string"},
                            "confidence": {"type": "number"},
                        },
                        "required": ["actor_name", "organization", "role", "signal_type",
                                     "stance", "influence", "description",
                                     "evidence_quote", "confidence"],
                        "additionalProperties": False,
                    },
                },
                "next_steps": {"type": "array", "items": {"type": "string"}},
                "open_questions": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["summary", "signals", "next_steps", "open_questions"],
            "additionalProperties": False,
        },
    },
}

EXTRACTION_RULES = """You extract deal signals from a sales rep's meeting debrief about a large,
multi-year infrastructure contract. Rules:
- Only report what the debrief says. Never invent a person, a number or a stance.
- evidence_quote must be copied word for word from the debrief.
- If a field is not stated, use "" (text) or "unknown" (enums).
- confidence is between 0 and 1: lower it when the rep hesitates ("je crois", "peut-être").
- Keep the language of the debrief for summary, description, next_steps and open_questions."""


def extract(text: str, name: str = "debrief") -> dict:
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[
            {"role": "developer", "content": EXTRACTION_RULES},
            {"role": "user", "content": f"Debrief:\n{text}"},
        ],
        response_format=SIGNALS_SCHEMA,
    )
    data = json.loads(resp.choices[0].message.content)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    show_usage(resp)
    (OUT / f"{name}_signals.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


# ---------------------------------------------------------------- 4. image
ORGCHART_SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "stakeholder_sketch",
        "schema": {
            "type": "object",
            "properties": {
                "people": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "role": {"type": "string"},
                            "organization": {"type": "string"},
                            "annotation": {"type": "string"},
                        },
                        "required": ["name", "role", "organization", "annotation"],
                        "additionalProperties": False,
                    },
                },
                "links": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "source": {"type": "string"},
                            "target": {"type": "string"},
                            "relation": {"type": "string"},
                        },
                        "required": ["source", "target", "relation"],
                        "additionalProperties": False,
                    },
                },
                "unreadable_parts": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["people", "links", "unreadable_parts"],
            "additionalProperties": False,
        },
    },
}


def read_image(path: str) -> dict:
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    b64 = base64.b64encode(Path(path).read_bytes()).decode()
    resp = client.chat.completions.create(
        model=CHAT_MODEL,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": (
                    "This is a hand-drawn stakeholder sketch from a sales meeting. "
                    "List every person (name, role, organization, any annotation like +, -, ?) "
                    "and every arrow or line between them (source, target, what it means). "
                    "Put anything you cannot read in unreadable_parts. Do not guess.")},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            ],
        }],
        response_format=ORGCHART_SCHEMA,
    )
    data = json.loads(resp.choices[0].message.content)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    show_usage(resp)
    (OUT / (Path(path).stem + "_sketch.json")).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return data


# ---------------------------------------------------------------- CLI
def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("command", choices=["ping", "transcribe", "extract", "image", "all"])
    p.add_argument("files", nargs="*")
    p.add_argument("--lang", default=None, help="ex : french (biais de langue pour la voix)")
    a = p.parse_args()

    if a.command == "ping":
        ping()
    elif a.command == "transcribe":
        transcribe(a.files[0], a.lang)
    elif a.command == "extract":
        f = Path(a.files[0])
        extract(f.read_text(encoding="utf-8"), f.stem)
    elif a.command == "image":
        read_image(a.files[0])
    elif a.command == "all":
        ping()
        print("\n--- Voix -> texte")
        text = transcribe(a.files[0], a.lang)
        print("\n--- Texte -> signaux")
        extract(text, Path(a.files[0]).stem)
        if len(a.files) > 1:
            print("\n--- Croquis -> parties prenantes")
            read_image(a.files[1])


if __name__ == "__main__":
    main()
