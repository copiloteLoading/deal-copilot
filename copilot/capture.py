"""Transcription d'un débrief vocal avec Muse Voice Transcribe.

L'API attend du WAV mono 16 bits à 16 ou 24 kHz. Le micro du navigateur et les fichiers
déposés arrivent souvent en stéréo 44,1 ou 48 kHz : on convertit en Python (sans ffmpeg).
Les noms propres du dossier sont passés en keywords pour être bien orthographiés.
Chaque transcription est mise en cache (hash de l'audio) : un même fichier n'est payé qu'une fois.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import wave

import numpy as np
import requests

from copilot import llm

TRANSCRIBE_URL = "https://api.meta.ai/v1/asr/transcribe"
MODEL = "muse-voice-transcribe-1.0"
TARGET_RATE = 16000
MAX_KEYWORD = 30          # limite de l'API par mot-clé (constatée le 29/10)


def fit_keywords(words: list[str]) -> list[str]:
    """Garde les mots-clés de 30 caractères au plus ; découpe les plus longs en noms propres."""
    out: list[str] = []
    for w in words:
        parts = [w] if len(w) <= MAX_KEYWORD else [
            p for p in w.replace("–", " ").split() if p[:1].isupper() and len(p) >= 3]
        out += [p for p in parts if p not in out and len(p) <= MAX_KEYWORD]
    return out


def to_wav16k(data: bytes) -> bytes:
    """Convertit un WAV quelconque (PCM 8/16/32 bits, mono ou stéréo) en WAV mono 16 bits 16 kHz."""
    with wave.open(io.BytesIO(data)) as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        raw = w.readframes(w.getnframes())
    dtype = {1: np.uint8, 2: np.int16, 4: np.int32}[width]
    x = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    if width == 1:
        x = (x - 128) / 128
    else:
        x = x / float(np.iinfo(dtype).max)
    x = x.reshape(-1, channels).mean(axis=1)                       # mono
    if rate != TARGET_RATE:                                         # rééchantillonnage linéaire
        n = int(len(x) * TARGET_RATE / rate)
        x = np.interp(np.linspace(0, len(x) - 1, n), np.arange(len(x)), x)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TARGET_RATE)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return out.getvalue()


def transcribe(audio: bytes, keywords: list[str] | None = None, language: str = "french") -> str:
    """Renvoie le texte d'un débrief vocal (WAV)."""
    wav = to_wav16k(audio)
    keywords = fit_keywords(keywords or [])
    key = hashlib.sha256(wav + json.dumps(keywords or []).encode()).hexdigest()[:16]
    cache = llm.CACHE_DIR / f"asr_{key}.json"
    if cache.exists():
        return json.loads(cache.read_text(encoding="utf-8"))["transcript"]
    if llm.provider() == "offline":
        raise llm.OfflineMiss("Transcription absente du cache (mode hors ligne).")

    request = {"mode": "PUSH_TO_TALK", "model": MODEL, "audioEncoding": "WAV",
               "languageBias": [language]}
    if keywords:
        request["keywords"] = keywords
    r = requests.post(
        TRANSCRIBE_URL,
        headers={"Authorization": f"Bearer {os.environ['MODEL_API_KEY']}"},
        files={"request": (None, json.dumps(request), "application/json"),
               "audio": ("debrief.wav", wav, "audio/wav")},
        timeout=300)
    if r.status_code != 200:
        raise RuntimeError(f"Transcription refusée ({r.status_code}) : {r.text[:300]}")
    result = r.json()
    llm.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"request": request, **result}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return result.get("transcript", "")
