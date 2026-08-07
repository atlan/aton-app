"""Symbole laden — mitgelieferte `i`-Arrays und eigene PNG-Dateien.

Nach aussen liefert die Verwaltung immer dasselbe: ein RGBA-Bild. Schwarz ist bei den
mitgelieferten Symbolen durchsichtig — genau so hat es der bisherige Renderer gehandhabt
(er hat "000000" beim Einsetzen uebersprungen), und nur so bleibt das Bild identisch.
Bei PNG-Dateien entscheidet deren eigener Alphakanal.
"""
from __future__ import annotations

import glob
import logging
import os
import re

from PIL import Image

from . import builtin_icons
from .const import USER_ICON_DIR

_LOG = logging.getLogger(__name__)


def entpacke_i(arr: list, anzahl: int) -> list[str]:
    """WLEDs `i`-Array in eine flache Pixelliste umrechnen.

    Regeln sind WLEDs eigene (json.cpp): zwei Ganzzahlen spannen einen Bereich auf, eine
    Farbe fuellt ihn; ohne vorangehenden Bereich faerbt sie genau ein Pixel, und der Zeiger
    laeuft weiter. Unveraendert aus dem pyscript-Renderer uebernommen.
    """
    px = ["000000"] * anzahl
    start = stop = 0
    gesetzt = 0
    for v in arr:
        if isinstance(v, int):
            if gesetzt == 0:
                start, gesetzt = abs(v), 1
            else:
                stop, gesetzt = abs(v), 2
        else:
            farbe = v if isinstance(v, str) else "%02x%02x%02x" % (v[0], v[1], v[2])
            if gesetzt < 2 or stop <= start:
                stop = start + 1
            while start < stop and start < anzahl:
                px[start] = farbe
                start += 1
            gesetzt = 0
    return px


def _hex2rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def pixel_zu_bild(pixel: list[str], breite: int, schwarz_transparent: bool = True) -> Image.Image:
    hoehe = max(1, len(pixel) // breite)
    img = Image.new("RGBA", (breite, hoehe), (0, 0, 0, 0))
    daten = []
    for p in pixel[: breite * hoehe]:
        if schwarz_transparent and (not p or p == "000000"):
            daten.append((0, 0, 0, 0))
        else:
            r, g, b = _hex2rgb(p)
            daten.append((r, g, b, 255))
    img.putdata(daten)
    return img


NAME_ERLAUBT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


class IconRegistry:
    def __init__(self) -> None:
        self._cache: dict[str, Image.Image] = {}
        self._dateien: dict[str, str] = {}
        self.neu_einlesen()

    def neu_einlesen(self) -> None:
        """Das Verzeichnis noch einmal durchsehen und den Zwischenspeicher leeren.

        ★ Wichtig, dass das am SELBEN Objekt passiert: die laufenden Anzeigen halten eine
        Referenz auf diese Verwaltung. Ein neues Objekt anzulegen wuerde bedeuten, alle
        Anzeigen neu aufzubauen — und damit Handauswahl und laufende Meldungen
        zuruecksetzen, nur weil jemand ein Symbol gezeichnet hat.
        """
        self._cache.clear()
        self._dateien.clear()
        if os.path.isdir(USER_ICON_DIR):
            for pfad in sorted(glob.glob(os.path.join(USER_ICON_DIR, "*"))):
                stamm, endung = os.path.splitext(os.path.basename(pfad))
                if endung.lower() in (".png", ".gif", ".bmp"):
                    self._dateien[stamm] = pfad
        _LOG.info("Symbole: %d mitgeliefert, %d eigene",
                  len(builtin_icons.icons), len(self._dateien))

    def namen(self) -> list[str]:
        return sorted(set(builtin_icons.icons) | set(self._dateien))

    def ist_eigen(self, name: str) -> bool:
        return name in self._dateien

    def datei(self, name: str) -> str | None:
        return self._dateien.get(name)

    # -- Schreiben ---------------------------------------------------------
    def speichere(self, name: str, bild: Image.Image) -> str:
        """Ein Symbol als PNG ablegen — mit Alphakanal.

        ⚠ Der Name wird geprueft, bevor er in einen Pfad geraet. Ein Name wie
        `../../configuration` waere sonst genau das, wonach er aussieht.
        """
        if not NAME_ERLAUBT.match(name):
            raise ValueError("Name: Buchstaben, Ziffern, '-' und '_', "
                             "beginnend mit Buchstabe oder Ziffer")
        os.makedirs(USER_ICON_DIR, exist_ok=True)
        pfad = os.path.join(USER_ICON_DIR, name + ".png")
        bild.convert("RGBA").save(pfad, "PNG")
        self.neu_einlesen()
        _LOG.info("Symbol '%s' gespeichert (%dx%d)", name, bild.width, bild.height)
        return pfad

    def loesche(self, name: str) -> bool:
        """Nur eigene Dateien. Ein mitgeliefertes Symbol kann man nicht wegwerfen —
        aber ein gleichnamiges eigenes zu loeschen bringt das mitgelieferte zurueck."""
        pfad = self._dateien.get(name)
        if not pfad:
            return False
        os.unlink(pfad)
        self.neu_einlesen()
        _LOG.info("Symbol '%s' geloescht", name)
        return True

    def get(self, name: str) -> Image.Image:
        if name in self._cache:
            return self._cache[name]

        if name in self._dateien:            # eigene Datei schlaegt Mitgeliefertes
            img = Image.open(self._dateien[name]).convert("RGBA")
        elif name in builtin_icons.icons:
            breite = builtin_icons.BREITEN.get(name, 8)
            roh = builtin_icons.icons[name]
            img = pixel_zu_bild(entpacke_i(roh, breite * 8), breite)
        else:
            raise KeyError(f"Symbol '{name}' nicht gefunden. Vorhanden: "
                           f"{', '.join(self.namen())}")

        self._cache[name] = img
        return img
