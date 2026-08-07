#!/usr/bin/env python3
"""Bitmap-Schriften des Systems einmalig in Pillows Format uebersetzen (Bauzeit).

Debian liefert Spleen und Terminus als gezippte PCF-Dateien. Pillow kann PCF lesen,
aber nur unkomprimiert und nur mit einem Extra-Schritt — den hier zur Bauzeit zu
erledigen spart ihn bei jedem Start und macht Fehler beim Bauen sichtbar statt im
Betrieb.

Ergebnis je Schrift: <name>.pil (Metriken) + <name>.pbm (Glyphen), ladbar mit
PIL.ImageFont.load(). Zeichenvorrat: 0..255, also inklusive Umlauten.
"""
from __future__ import annotations

import glob
import gzip
import io
import os
import sys

from PIL import BdfFontFile, PcfFontFile

HIER = os.path.dirname(os.path.abspath(__file__))

QUELLEN = (
    "/usr/share/fonts/X11/misc/spleen-*.pcf.gz",
    "/usr/share/fonts/X11/misc/ter-*.pcf.gz",
    os.path.join(HIER, "..", "fonts_src", "*.bdf"),      # eigene, im Repo gepflegt
)


def uebersetze(pfad: str, ziel_dir: str) -> str | None:
    name = os.path.basename(pfad)
    for endung in (".pcf.gz", ".pcf", ".bdf"):
        if name.endswith(endung):
            name = name[: -len(endung)]
            break
    ziel = os.path.join(ziel_dir, name + ".pil")
    try:
        roh = gzip.open(pfad, "rb").read() if pfad.endswith(".gz") else open(pfad, "rb").read()
        bauer = BdfFontFile.BdfFontFile if pfad.endswith(".bdf") else PcfFontFile.PcfFontFile
        schrift = bauer(io.BytesIO(roh))
        schrift.save(ziel)
    except Exception as e:  # eine kaputte Schrift darf den Bau nicht kippen
        print(f"  ! {name}: {type(e).__name__}: {e}", file=sys.stderr)
        return None
    return name


def main() -> int:
    ziel_dir = sys.argv[1] if len(sys.argv) > 1 else "/opt/aton/fonts"
    os.makedirs(ziel_dir, exist_ok=True)

    gefunden = sorted({p for muster in QUELLEN for p in glob.glob(muster)})
    if not gefunden:
        print("Keine PCF-Schriften gefunden — sind fonts-spleen/xfonts-terminus installiert?",
              file=sys.stderr)
        return 1

    fertig = [n for n in (uebersetze(p, ziel_dir) for p in gefunden) if n]
    print(f"{len(fertig)} Schriften uebersetzt nach {ziel_dir}:")
    for n in fertig:
        print(f"  - {n}")
    return 0 if fertig else 1


if __name__ == "__main__":
    raise SystemExit(main())
