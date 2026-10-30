"""Transcription d'un débrief vocal avec Muse Voice Transcribe.

L'API attend du WAV mono 16 bits à 16 ou 24 kHz. Le micro du navigateur et les fichiers
déposés arrivent souvent en stéréo 44,1 ou 48 kHz : on convertit en Python (sans ffmpeg).
Les noms propres du dossier sont passés en keywords pour être bien orthographiés.
Le commercial dicte où il peut (transports, douche). Mesuré dans eval/noise.md : Muse Voice
Transcribe résiste bien au bruit, et notre débruitage (denoise) n'apporte pas de gain fiable ;
il n'est donc pas appliqué par défaut. estimate_snr sert à prévenir quand le bruit est très fort.
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


def read_wav16k(data: bytes) -> np.ndarray:
    """Lit un WAV quelconque (PCM 8/16/32 bits, mono ou stéréo) en signal mono 16 kHz entre -1 et 1."""
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
    return x


def write_wav16k(x: np.ndarray) -> bytes:
    """Signal mono 16 kHz -> WAV mono 16 bits, le format attendu par l'API."""
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TARGET_RATE)
        w.writeframes((np.clip(x, -1, 1) * 32767).astype(np.int16).tobytes())
    return out.getvalue()


def to_wav16k(data: bytes) -> bytes:
    """Convertit un WAV quelconque en WAV mono 16 bits 16 kHz."""
    return write_wav16k(read_wav16k(data))


def _stft(x: np.ndarray, n: int, hop: int) -> np.ndarray:
    w = np.sqrt(np.hanning(n + 1)[:-1])
    pad = np.concatenate([np.zeros(n), x, np.zeros(n)])
    frames = np.lib.stride_tricks.sliding_window_view(pad, n)[::hop]
    return np.fft.rfft(frames * w, axis=1)


def _istft(X: np.ndarray, n: int, hop: int, length: int) -> np.ndarray:
    w = np.sqrt(np.hanning(n + 1)[:-1])
    frames = np.fft.irfft(X, n=n, axis=1) * w
    out = np.zeros(hop * (len(frames) - 1) + n)
    norm = np.zeros_like(out)
    for i, f in enumerate(frames):                                  # addition-recouvrement
        out[i * hop:i * hop + n] += f
        norm[i * hop:i * hop + n] += w ** 2
    return (out / np.maximum(norm, 1e-8))[n:n + length]


N_FFT, HOP = 512, 128                    # 32 ms à 16 kHz, recouvrement 75 %
# La puissance d'un bruit gaussien dans une case temps-fréquence suit une loi exponentielle :
# son 10e centile vaut -ln(0,9) ≈ 0,105 fois sa moyenne. On corrige ce biais.
PCT10_TO_MEAN = 1 / -np.log(0.9)
NOISY_BELOW_DB = 5.0                     # sous ce SNR estimé, on prévient le commercial


def _noise_psd(power: np.ndarray) -> np.ndarray:
    """Spectre moyen du bruit, estimé sur les moments les plus calmes de chaque fréquence :
    la parole a des pauses, le bruit de fond est permanent."""
    return np.percentile(power, 10, axis=0) * PCT10_TO_MEAN + 1e-12


def estimate_snr(x: np.ndarray) -> float:
    """Rapport signal sur bruit estimé à l'aveugle (dB), sans connaître le signal propre."""
    power = np.abs(_stft(x, N_FFT, HOP)) ** 2
    noise, total = _noise_psd(power).sum(), power.sum(axis=1).mean()
    return float(10 * np.log10(max(total - noise, 1e-12) / noise))


def denoise(x: np.ndarray, rate: int = TARGET_RATE, over: float = 0.2, floor: float = 0.1,
            smooth: float = 0.6) -> np.ndarray:
    """Débruitage léger pour une dictée faite dans les transports ou sous la douche.

    1. Passe-haut à 90 Hz : supprime le grondement (moteur, roulement) sans toucher la voix.
    2. Spectre du bruit estimé sur les moments calmes (_noise_psd).
    3. Gain de type Wiener avec soustraction douce (over), plancher (floor) et lissage dans
       le temps (smooth) pour limiter le « bruit musical » qui gêne la reconnaissance.
    Une soustraction complète (over = 1) améliore davantage le SNR mais dégrade la
    transcription (artefacts) : Muse Voice Transcribe préfère un son peu retouché (eval/noise.md).
    """
    n, hop = N_FFT, HOP
    X = _stft(x, n, hop)
    freqs = np.fft.rfftfreq(n, 1 / rate)
    X[:, freqs < 90] *= 0.0
    power = np.abs(X) ** 2
    noise = _noise_psd(power)
    gain = np.maximum(1 - over * noise / (power + 1e-12), floor)
    for t in range(1, len(gain)):                                   # lissage temporel du gain
        gain[t] = smooth * gain[t - 1] + (1 - smooth) * gain[t]
    return _istft(X * gain, n, hop, len(x))


def transcribe(audio: bytes, keywords: list[str] | None = None, language: str = "english",
               clean: bool = False) -> str:
    """Renvoie le texte d'un débrief vocal (WAV). clean=True applique denoise() avant l'envoi."""
    x = read_wav16k(audio)
    if clean:
        x = denoise(x)
    wav = write_wav16k(x)
    keywords = fit_keywords(keywords or [])
    key = hashlib.sha256(wav + json.dumps(keywords or []).encode()).hexdigest()[:16]
    cache = llm.CACHE_DIR / f"asr_{key}.json"
    found = llm.cache_file(cache.name)
    if found:
        return json.loads(found.read_text(encoding="utf-8"))["transcript"]
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
        raise RuntimeError(f"Transcription refused ({r.status_code}): {r.text[:300]}")
    result = r.json()
    llm.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"request": request, **result}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    return result.get("transcript", "")
