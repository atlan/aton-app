"""Schriftenverwaltung.

Drei Quellen, in dieser Reihenfolge durchsucht:
  1. die eingebaute 5x3-Schrift (Name `5x3`) — pixelgleich zur bisherigen Anlage
  2. die zur Bauzeit uebersetzten Systemschriften (`spleen-5x8`, `spleen-6x12`,
     `spleen-8x16`, `ter-…`) — echte Pixel-Schriften inkl. Umlauten
  3. eigene Dateien in `/homeassistant/aton_fonts` (.pil, .bdf, .pcf, .ttf, .otf)

Vektor-Schriften (.ttf/.otf) brauchen eine Groesse: `arial@8`. Sie werden ohne
Kantenglaettung gerastert (`fontmode = "1"`) — auf einer LED-Matrix ist ein halbheller
Pixel kein Gewinn, sondern Matsch.
"""
from __future__ import annotations

import glob
import io
import logging
import os

from PIL import BdfFontFile, ImageDraw, ImageFont, PcfFontFile

from . import builtin_font
from .const import DATA_DIR, FONT_DIR, USER_FONT_DIR

_LOG = logging.getLogger(__name__)


# Vorgaben je mitgelieferter Schrift. Sie sind eine Eigenschaft der SCHRIFT, nicht des
# Programms: in 5 px Hoehe sind Kleinbuchstaben unlesbar und ueber einem vollhohen
# Buchstaben ist kein Platz fuer Umlautpunkte — bei spleen-8x16 gilt beides nicht.
# Ueberschreibbar im YAML-Abschnitt `fonts:`.
SCHRIFT_VORGABEN: dict[str, dict[str, bool]] = {
    "5x3": {"uppercase": True, "transliterate": True},
    "matrix5x3": {"uppercase": True, "transliterate": True},
}

UMSCHRIFT = (("Ä", "AE"), ("Ö", "OE"), ("Ü", "UE"), ("ß", "SS"))


def _regeln(text: str, uppercase: bool, transliterate: bool) -> str:
    text = str(text)
    if uppercase:
        text = text.upper()
    if transliterate:
        for von, nach in UMSCHRIFT:
            text = text.replace(von, nach)
    return text


class Font:
    """Gemeinsame Schnittstelle fuer Bitmap- und Vektor-Schriften."""

    name = "?"
    height = 0

    def prepare(self, text: str) -> str:
        return str(text)

    def measure(self, text: str) -> tuple[int, int]:
        raise NotImplementedError

    def draw(self, d: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
             color: tuple[int, int, int]) -> None:
        raise NotImplementedError


class Builtin5x3(Font):
    name = "5x3"
    height = builtin_font.HOEHE

    def prepare(self, text: str) -> str:
        return builtin_font.prepare(text)

    def measure(self, text: str) -> tuple[int, int]:
        return builtin_font.breite(self.prepare(text)), self.height

    def draw(self, d, xy, text, color):
        x0, y0 = xy
        for y, linie in enumerate(builtin_font.zeilen(self.prepare(text))):
            for x, p in enumerate(linie):
                if p == "1":
                    d.point((x0 + x, y0 + y), fill=color)


class PilFont(Font):
    """Bitmap- oder Vektor-Schrift ueber Pillow."""

    def __init__(self, name: str, font: ImageFont.ImageFont, latin1: bool,
                 uppercase: bool = False, transliterate: bool = False):
        self.name = name
        self._font = font
        self._latin1 = latin1
        self._uppercase = uppercase
        self._transliterate = transliterate
        try:
            self.height = font.getbbox("Mg")[3]
        except Exception:
            self.height = 8

    def prepare(self, text: str) -> str:
        text = _regeln(text, self._uppercase, self._transliterate)
        if not self._latin1:
            return text
        # Bitmap-Schriften kennen nur 0..255. Unbekanntes ersetzen statt abstuerzen.
        return text.encode("latin-1", "replace").decode("latin-1")

    def measure(self, text: str) -> tuple[int, int]:
        box = self._font.getbbox(self.prepare(text))
        return box[2] - box[0], box[3] - box[1]

    def draw(self, d, xy, text, color):
        d.fontmode = "1"          # keine Kantenglaettung
        d.text(xy, self.prepare(text), fill=color, font=self._font)


class FontRegistry:
    def __init__(self, optionen: dict[str, dict] | None = None) -> None:
        self._optionen = optionen or {}
        self._fonts: dict[str, Font] = {"5x3": Builtin5x3()}
        self._dateien: dict[str, str] = {}
        self._suche()

    def _regel_fuer(self, name: str) -> tuple[bool, bool]:
        stamm = name.partition("@")[0]
        regeln = dict(SCHRIFT_VORGABEN.get(stamm, {}))
        regeln.update(self._optionen.get(name, self._optionen.get(stamm, {})))
        return bool(regeln.get("uppercase")), bool(regeln.get("transliterate"))

    # -- Aufbau ------------------------------------------------------------
    def _suche(self) -> None:
        for ordner in (FONT_DIR, USER_FONT_DIR):
            if not os.path.isdir(ordner):
                continue
            for pfad in sorted(glob.glob(os.path.join(ordner, "*"))):
                stamm, endung = os.path.splitext(os.path.basename(pfad))
                if endung.lower() in (".pil", ".bdf", ".pcf", ".ttf", ".otf"):
                    self._dateien.setdefault(stamm, pfad)
        _LOG.info("Schriften gefunden: %s", ", ".join(sorted(self.namen())))

    def namen(self) -> list[str]:
        return sorted(set(self._fonts) | set(self._dateien))

    # -- Zugriff -----------------------------------------------------------
    def get(self, name: str | None) -> Font:
        name = (name or "5x3").strip()
        if name in self._fonts:
            return self._fonts[name]

        stamm, _, groesse = name.partition("@")
        pfad = self._dateien.get(stamm)
        if pfad is None:
            raise KeyError(f"Schrift '{name}' nicht gefunden. Vorhanden: "
                           f"{', '.join(self.namen())}")

        font = self._lade(pfad, int(groesse) if groesse.isdigit() else None)
        latin1 = os.path.splitext(pfad)[1].lower() in (".pil", ".bdf", ".pcf")
        gross, umschrift = self._regel_fuer(name)
        self._fonts[name] = PilFont(name, font, latin1, gross, umschrift)
        return self._fonts[name]

    @staticmethod
    def _lade(pfad: str, groesse: int | None):
        endung = os.path.splitext(pfad)[1].lower()
        if endung in (".ttf", ".otf"):
            if not groesse:
                raise ValueError(
                    f"'{os.path.basename(pfad)}' ist eine Vektor-Schrift und braucht eine "
                    f"Groesse, z.B. '{os.path.splitext(os.path.basename(pfad))[0]}@8'")
            return ImageFont.truetype(pfad, groesse)
        if endung == ".pil":
            return ImageFont.load(pfad)
        # .bdf / .pcf zur Laufzeit uebersetzen (nur fuer eigene Dateien noetig).
        # Pillow kann eine FontFile nur ueber die Platte in eine ImageFont ueberfuehren,
        # deshalb der Zwischenschritt. /data ist immer beschreibbar, der Font-Ordner des
        # Benutzers moeglicherweise nicht.
        with open(pfad, "rb") as fh:
            roh = io.BytesIO(fh.read())
        bauer = BdfFontFile.BdfFontFile if endung == ".bdf" else PcfFontFile.PcfFontFile
        datei = bauer(roh)
        cache = os.path.join(DATA_DIR, "fontcache")
        os.makedirs(cache, exist_ok=True)
        ziel = os.path.join(cache, os.path.splitext(os.path.basename(pfad))[0] + ".pil")
        datei.save(ziel)
        return ImageFont.load(ziel)
