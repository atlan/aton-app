#!/usr/bin/env python3
"""Nachweis, dass die erzeugte BDF-Datei pixelgleich zur eingebauten 5x3-Schleife zeichnet.

Verglichen wird jedes einzelne Zeichen und dazu eine Reihe echter Kacheltexte. Erst wenn
das 0 Abweichungen ergibt, darf die BDF-Fassung die eingebaute ersetzen — vorher ist sie
nur eine Behauptung.
"""
from __future__ import annotations

import io
import os
import sys

from PIL import BdfFontFile, Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from panel import builtin_font                                    # noqa: E402
from panel.fonts import Builtin5x3                                # noqa: E402

PROBEN = [
    "20.6°C", "80.0%", "2.49", "0.6", "25.0°C", "65.7%", "2.5", "NW", "737W",
    "12131.1", "84%", "96%", "Eimer", "Streu", "OK", "14:37", "31",
    "0W", "23W", "5%", "22.7°C", "-12.5°C", "1234567890",
    "Waschmaschine fertig", "ABCDEFGHIJKLMNOPQRSTUVWXYZ",
]


def bdf_font(pfad: str) -> ImageFont.ImageFont:
    with open(pfad, "rb") as fh:
        datei = BdfFontFile.BdfFontFile(io.BytesIO(fh.read()))
    ziel = os.path.join(os.path.dirname(pfad), "_check_matrix5x3.pil")
    datei.save(ziel)
    return ImageFont.load(ziel)


def male_alt(text: str, breite: int, hoehe: int) -> Image.Image:
    bild = Image.new("RGB", (breite, hoehe), (0, 0, 0))
    d = ImageDraw.Draw(bild)
    Builtin5x3().draw(d, (0, 0), text, (255, 255, 255))
    return bild


def male_bdf(font, text: str, breite: int, hoehe: int) -> Image.Image:
    bild = Image.new("RGB", (breite, hoehe), (0, 0, 0))
    d = ImageDraw.Draw(bild)
    d.fontmode = "1"
    d.text((0, 0), builtin_font.prepare(text), fill=(255, 255, 255), font=font)
    return bild


def vergleiche(font, text: str) -> int:
    breite = max(1, builtin_font.breite(builtin_font.prepare(text)) + 4)
    hoehe = 10
    a = male_alt(text, breite, hoehe)
    b = male_bdf(font, text, breite, hoehe)
    return sum(1 for pa, pb in zip(a.getdata(), b.getdata()) if pa != pb)


def zeige(font, text: str) -> None:
    breite = max(1, builtin_font.breite(builtin_font.prepare(text)) + 4)
    a, b = male_alt(text, breite, 10), male_bdf(font, text, breite, 10)
    for name, bild in (("eingebaut", a), ("BDF", b)):
        print(f"  {name}:")
        for y in range(builtin_font.HOEHE + 2):
            print("    " + "".join("#" if bild.getpixel((x, y))[0] else "."
                                   for x in range(breite)))


def main() -> int:
    hier = os.path.dirname(os.path.abspath(__file__))
    pfad = os.path.abspath(os.path.join(hier, "..", "fonts_src", "matrix5x3.bdf"))
    if not os.path.exists(pfad):
        print(f"{pfad} fehlt — erst tools/make_5x3_bdf.py laufen lassen", file=sys.stderr)
        return 2
    font = bdf_font(pfad)

    fehler = 0
    for ch in sorted(builtin_font.GLYPHEN):
        n = vergleiche(font, ch)
        if n:
            fehler += 1
            print(f"Zeichen {ch!r} (U+{ord(ch):04X}): {n} Pixel Unterschied")
    print(f"Einzelzeichen: {len(builtin_font.GLYPHEN) - fehler}/{len(builtin_font.GLYPHEN)} gleich")

    schlecht = []
    for text in PROBEN:
        n = vergleiche(font, text)
        if n:
            schlecht.append((text, n))
    print(f"Kacheltexte:   {len(PROBEN) - len(schlecht)}/{len(PROBEN)} gleich")
    for text, n in schlecht[:5]:
        print(f"\n{text!r}: {n} Pixel Unterschied")
        zeige(font, text)

    for rest in ("_check_matrix5x3.pil", "_check_matrix5x3.pbm"):
        weg = os.path.join(os.path.dirname(pfad), rest)
        if os.path.exists(weg):
            os.unlink(weg)
    return 0 if not fehler and not schlecht else 1


if __name__ == "__main__":
    raise SystemExit(main())
