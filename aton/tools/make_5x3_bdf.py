#!/usr/bin/env python3
"""Die eingebaute 5x3-Schrift als BDF-Datei ausschreiben.

Damit wird aus der Python-Tabelle eine **echte Schriftdatei**: sie laeuft ueber denselben
Weg wie Spleen und Terminus, laesst sich mit einem Font-Editor weiterpflegen und um
Zeichen ergaenzen, ohne dass jemand Python anfasst.

Die Breite ist je Zeichen verschieden (N ist 4 breit, '.' nur 1) — BDF kann das ueber
`DWIDTH` je Glyph. Der Zeichenabstand von 1 px steckt wie bisher im Vorschub, nicht im
Bild: `DWIDTH = Bildbreite + 1`.

Nach dem Erzeugen gehoert die Datei ins Repo (fonts_src/). Ob Pillow sie **pixelgleich**
zur bisherigen Schleife setzt, prueft `tools/check_5x3_bdf.py` — nicht glauben, messen.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from panel import builtin_font  # noqa: E402

NAME = "matrix5x3"
HOEHE = builtin_font.HOEHE


def glyph_bitmap(muster: list[str]) -> tuple[list[str], int]:
    """Bitmuster in BDF-Hexzeilen umsetzen (MSB links, auf volle Bytes aufgefuellt)."""
    breite = len(muster[0])
    bytes_je_zeile = (breite + 7) // 8
    zeilen = []
    for zeile in muster:
        wert = 0
        for i, p in enumerate(zeile):
            if p == "1":
                wert |= 1 << (bytes_je_zeile * 8 - 1 - i)
        zeilen.append(f"{wert:0{bytes_je_zeile * 2}X}")
    return zeilen, breite


def schreibe(ziel: str) -> int:
    zeichen = sorted(builtin_font.GLYPHEN.items(), key=lambda kv: ord(kv[0]))
    max_breite = max(len(m[0]) for _, m in zeichen)

    aus = [
        "STARTFONT 2.1",
        "COMMENT Erzeugt aus panel/builtin_font.py - nicht von Hand aendern,",
        "COMMENT sondern dort oder mit einem Font-Editor (dann diesen Hinweis loeschen).",
        f"FONT -matrixpanel-{NAME}-medium-r-normal--{HOEHE}-50-75-75-p-30-iso10646-1",
        f"SIZE {HOEHE} 75 75",
        f"FONTBOUNDINGBOX {max_breite} {HOEHE} 0 0",
        "STARTPROPERTIES 4",
        f"FONT_ASCENT {HOEHE}",
        "FONT_DESCENT 0",
        f"DEFAULT_CHAR {ord(' ')}",
        "SPACING \"P\"",
        "ENDPROPERTIES",
        f"CHARS {len(zeichen)}",
    ]

    for ch, muster in zeichen:
        bitmap, breite = glyph_bitmap(muster)
        aus += [
            f"STARTCHAR U+{ord(ch):04X}",
            f"ENCODING {ord(ch)}",
            "SWIDTH 500 0",
            f"DWIDTH {breite + 1} 0",          # +1 = der Zeichenabstand wie bisher
            f"BBX {breite} {HOEHE} 0 0",
            "BITMAP",
            *bitmap,
            "ENDCHAR",
        ]
    aus.append("ENDFONT")

    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    with open(ziel, "w", encoding="ascii") as fh:
        fh.write("\n".join(aus) + "\n")
    return len(zeichen)


if __name__ == "__main__":
    ziel = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "fonts_src", f"{NAME}.bdf")
    ziel = os.path.abspath(ziel)
    print(f"{schreibe(ziel)} Zeichen geschrieben nach {ziel}")
