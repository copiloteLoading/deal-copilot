"""Génère les deux photos d'exemple, entièrement fictives : des notes manuscrites et un tableau blanc.

Rendu « photo » : papier ou tableau légèrement tourné, vignettage, bruit, léger flou.
Polices manuscrites de Windows (Ink Free, Segoe Print) : à lancer sous Windows.

Usage : .\\.venv\\Scripts\\python.exe samples\\make_samples.py
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

F = "C:/Windows/Fonts/"
OUT = Path(__file__).resolve().parent
rng = np.random.default_rng(5)


def photo_effect(img, angle, bg, light=(0.45, 0.4), noise=4, blur=0.7, scale=0.75):
    img = img.rotate(angle, resample=Image.BICUBIC, expand=True, fillcolor=bg)
    a = np.asarray(img).astype(float)
    h, w = a.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    vign = 1 - 0.3 * (((xx - w * light[0]) / w) ** 2 + ((yy - h * light[1]) / h) ** 2) * 2.2
    a = a * vign[..., None] + rng.normal(0, noise, a.shape)
    img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(blur))
    return img.resize((int(img.width * scale), int(img.height * scale)))


def notes() -> None:
    W, H = 1500, 2150
    img = Image.new("RGB", (W, H), (252, 251, 245))
    d = ImageDraw.Draw(img)
    for y in range(230, H - 60, 62):                               # papier ligné
        d.line((60, y, W - 60, y), fill=(190, 210, 235), width=2)
    d.line((170, 0, 170, H), fill=(235, 160, 160), width=3)        # marge
    hand = ImageFont.truetype(F + "Inkfree.ttf", 46)
    big = ImageFont.truetype(F + "Inkfree.ttf", 54)
    lines = [
        ("Mtg ADB  -  22/10/2026", big),
        ("Present: Thomas Riou (rel. manager),", hand),
        ("   Paul Ternaud (ADB legal), me", hand),
        ("", hand),
        ("- env. impact study: final version", hand),
        ("   expected BEFORE credit committee", hand),
        ("- T. Riou: \"no financing until the", hand),
        ("   study is approved\"", hand),
        ("- bank guarantee on the payment plan ->", hand),
        ("   he finds the idea interesting, dig into it", hand),
        ("- credit committee: mid-December ?? (tbc)", hand),
        ("- P. Ternaud wants to review penalty clauses", hand),
        ("", hand),
        ("TO DO: send study summary to T. Riou", big),
        ("   before 15/11 !", big),
    ]
    y = 160
    for text, font in lines:
        d.text((200 + rng.integers(-6, 7), y + rng.integers(-4, 5)), text, font=font, fill=(25, 45, 120))
        y += 124
    photo_effect(img, 1.6, (95, 85, 70), light=(0.4, 0.35)).save(OUT / "notes_bank_meeting.jpg", quality=82)


def whiteboard() -> None:
    W, H = 2000, 1250
    img = Image.new("RGB", (W, H), (244, 246, 245))
    d = ImageDraw.Draw(img)
    mk = ImageFont.truetype(F + "segoepr.ttf", 46)
    mk_b = ImageFont.truetype(F + "segoeprb.ttf", 58)
    blue, red, green, black = (30, 70, 170), (200, 40, 40), (30, 130, 60), (35, 35, 35)
    d.text((90, 60), "Phasing workshop - Nordlink consortium", font=mk_b, fill=black)
    d.line((90, 150, 1300, 160), fill=black, width=5)
    d.rounded_rectangle((110, 250, 720, 450), 30, outline=blue, width=7)
    d.text((150, 285), "Phase 1: 2027", font=mk_b, fill=blue)
    d.text((150, 365), "Port-Lazen -> 240 km", font=mk, fill=blue)
    d.rounded_rectangle((980, 250, 1600, 450), 30, outline=blue, width=7)
    d.text((1020, 285), "Phase 2: 2028", font=mk_b, fill=blue)
    d.text((1020, 365), "-> Kerlis 180 km", font=mk, fill=blue)
    d.line((730, 350, 960, 350), fill=blue, width=7)
    d.polygon([(960, 330), (1000, 350), (960, 370)], fill=blue)
    d.text((120, 560), "Yann: penalties OK", font=mk, fill=green)
    d.text((120, 650), "Julien: \"repeaters = the right choice\"", font=mk, fill=green)
    d.text((120, 760), "Sophie L.: OK only if spread over 4 years ?", font=mk, fill=red)
    d.text((120, 850), "Claire: supplier chosen at January committee", font=mk, fill=black)
    d.ellipse((1380, 640, 1880, 900), outline=red, width=7)
    d.text((1440, 700), "RISK:", font=mk_b, fill=red)
    d.text((1440, 780), "Baltis budget !!", font=mk_b, fill=red)
    d.text((120, 1010), "-> propose phasing + bank guarantee", font=mk_b, fill=blue)
    photo_effect(img, -1.2, (120, 120, 118), light=(0.55, 0.45), noise=3, blur=0.9, scale=0.7).save(
        OUT / "whiteboard_phasing.jpg", quality=82)


if __name__ == "__main__":
    notes()
    whiteboard()
    print("ok")
