"""Dictée dans le bruit : Muse Voice Transcribe résiste-t-il, et le débruitage aide-t-il ?

Le commercial dicte son débrief là où il est (transports, douche, voiture). On prend le débrief
du scénario piège (texte de référence connu), on y ajoute trois bruits synthétiques à plusieurs
rapports signal sur bruit (SNR), puis on transcrit avec et sans capture.denoise().

Bruits (générés ici, aucune donnée externe) :
  transport  bruit brun (grondement grave) + ronflement moteur à 50/100/150 Hz
  douche     bruit large bande 500 Hz – 8 kHz dont l'intensité fluctue
  brouhaha   4 copies du débrief lui-même, inversées et décalées : des voix sans mots

Mesures : taux d'erreur sur les mots (WER) par rapport au texte de référence, et part des
noms propres du dossier retrouvés (ce dont l'extraction a besoin).

Usage : .\\.venv\\Scripts\\python.exe -m eval.noise
Il faut le fichier outputs/debrief_piege.wav (non publié : *.wav est exclu du dépôt).
Mesure faite le 29 octobre sur la version française du dossier (avant le passage en anglais) ;
les mots-clés du dossier ayant changé depuis, une nouvelle exécution refait les transcriptions.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from copilot import capture, memory, pipeline

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "outputs" / "debrief_piege.wav"
# mesuré sur la version française du débrief piège (enregistrement et texte de l'époque)
REFERENCE = Path(__file__).resolve().parent / "noise_reference_fr.txt"
RESULTS = Path(__file__).resolve().parent
RATE = capture.TARGET_RATE
SNRS = [10, 5, 0]
NAMES = ["Claire Dantec", "Julien Marec", "Yann Le Goff", "Sophie Lenoir", "Thomas Riou",
         "Nordlink", "Port-Aven", "Kerlis"]   # enregistrement fait avant le renommage en Port-Lazen


def make_noise(kind: str, speech: np.ndarray) -> np.ndarray:
    rng = np.random.default_rng(7)
    n, t = len(speech), np.arange(len(speech)) / RATE
    if kind == "transport":
        brown = np.cumsum(rng.standard_normal(n))
        brown -= np.convolve(brown, np.ones(800) / 800, mode="same")   # retire la dérive très lente
        hum = sum(np.sin(2 * np.pi * f * t) / k for k, f in enumerate((50, 100, 150), 1))
        return brown / brown.std() + 0.5 * hum
    if kind == "douche":
        spec = np.fft.rfft(rng.standard_normal(n))
        f = np.fft.rfftfreq(n, 1 / RATE)
        spec[(f < 500) | (f > 8000)] = 0
        x = np.fft.irfft(spec, n)
        return x * (1 + 0.3 * np.sin(2 * np.pi * 0.7 * t))
    if kind == "brouhaha":
        rev = speech[::-1]
        return sum(np.roll(rev, int(RATE * s)) for s in (0, 3.1, 7.7, 12.9))
    raise ValueError(kind)


def mix(speech: np.ndarray, noise: np.ndarray, snr_db: float) -> np.ndarray:
    gain = np.sqrt(np.mean(speech ** 2) / (np.mean(noise ** 2) * 10 ** (snr_db / 10)))
    x = speech + gain * noise
    return x / max(1.0, np.abs(x).max())


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return re.findall(r"[a-z0-9]+", text)


def wer(ref: str, hyp: str) -> float:
    r, h = words(ref), words(hyp)
    d = np.arange(len(h) + 1)
    for i in range(1, len(r) + 1):                                  # distance d'édition sur les mots
        prev, d[0] = d.copy(), i
        for j in range(1, len(h) + 1):
            d[j] = min(prev[j] + 1, d[j - 1] + 1, prev[j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(h)] / len(r)


def names_found(hyp: str) -> float:
    joined = " ".join(words(hyp))
    return float(np.mean([" ".join(words(n)) in joined for n in NAMES]))


def run() -> dict:
    conn = memory.connect(":memory:")
    deal_id = memory.import_deal(conn, pipeline.DEMO_DIR)
    keywords = memory.keywords(conn, deal_id)
    reference = REFERENCE.read_text(encoding="utf-8")
    speech = capture.read_wav16k(AUDIO.read_bytes())
    speech = speech / np.abs(speech).max() * 0.5

    cases = [("propre", None, False)] + [(k, s, d) for k in ("transport", "douche", "brouhaha")
                                          for s in SNRS for d in (False, True)]

    def one(case):
        kind, snr, den = case
        x = speech if snr is None else mix(speech, make_noise(kind, speech), snr)
        est = capture.estimate_snr(x)
        text = capture.transcribe(capture.write_wav16k(x), keywords, language="french", clean=den)
        return {"noise": kind, "snr": snr, "denoised": den, "estimated_snr": est,
                "wer": wer(reference, text),
                "names": names_found(text), "transcript": text}

    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(one, cases))
    return {"rows": rows}


def report(res: dict) -> str:
    rows = res["rows"]
    clean = rows[0]
    lines = ["# Dictée dans le bruit", "",
             "Débrief du scénario piège (52 s), bruits synthétiques ajoutés, transcription par "
             "Muse Voice Transcribe avec les noms du dossier en mots-clés.", "",
             f"Sans bruit : WER {clean['wer']:.0%}, noms propres retrouvés {clean['names']:.0%}.", "",
             "| Bruit | SNR réel | SNR estimé | WER brut | WER débruité | Noms (brut / débruité) |",
             "|---|---|---|---|---|---|"]
    for r in rows[1:]:
        if r["denoised"]:
            continue
        d = next(x for x in rows if x["noise"] == r["noise"] and x["snr"] == r["snr"] and x["denoised"])
        lines.append(f"| {r['noise']} | {r['snr']} dB | {r['estimated_snr']:.1f} dB | {r['wer']:.0%} | "
                     f"{d['wer']:.0%} | {r['names']:.0%} / {d['names']:.0%} |")
    lines += ["", "Lecture : Muse Voice Transcribe résiste bien au bruit (les noms du dossier sont "
              "retrouvés comme sans bruit). Le débruitage n'apporte pas de gain fiable : d'un essai à "
              "l'autre, la transcription varie autant que l'effet du filtre (transport à 0 dB : 4 % avec "
              "une soustraction de 0,21, 10 % avec 0,2 ; une soustraction complète améliore le SNR mais "
              "dégrade la transcription). Il n'est donc pas appliqué par défaut ; le SNR estimé sert à "
              "prévenir le commercial quand le bruit est très fort. Limites : un seul enregistrement "
              "(voix de synthèse), bruits synthétiques, un essai par cas."]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    res = run()
    (RESULTS / "noise.json").write_text(json.dumps(res, ensure_ascii=False, indent=2), encoding="utf-8")
    text = report(res)
    (RESULTS / "noise.md").write_text(text, encoding="utf-8")
    print(text)
