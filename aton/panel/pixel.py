"""Bild <-> WLED-Pixeldarstellung. Bewusst ohne Netz-Abhaengigkeit.

Getrennt von `wled.py`, damit sich die Umrechnung ohne aiohttp testen laesst — der
Pixelvergleich gegen den alten Renderer laeuft so auf jedem Rechner.
"""
from __future__ import annotations

from PIL import Image


def bild_zu_pixeln(bild: Image.Image) -> list[str]:
    """Bild in die flache Farbliste umrechnen, die WLEDs `i`-Format erwartet."""
    return ["%02x%02x%02x" % px for px in bild.convert("RGB").getdata()]


def laeufe_kodieren(pixel: list[str], mit_schwarz: bool = False) -> list:
    """Bild als WLED-Bereichsliste [start, stop, farbe, ...].

    `mit_schwarz=False` laesst schwarze Laeufe weg — sinnvoll auf einer frisch geleerten
    Flaeche, wo Schwarz ohnehin schon steht.

    ★ `mit_schwarz=True` kodiert JEDEN Lauf und macht das Ergebnis damit vollstaendig:
    es beschreibt die Flaeche, statt sie nur zu ergaenzen. Genau das erlaubt ein Vollbild
    OHNE vorheriges Schwarzfuellen — und das Schwarzfuellen war die Ursache des
    Flackerns, weil die Matrix zwischen Leeren und Neuaufbau sichtbar dunkel war.
    """
    arr: list = []
    s = 0
    for i in range(1, len(pixel) + 1):
        if i == len(pixel) or pixel[i] != pixel[s]:
            if mit_schwarz or pixel[s] != "000000":
                arr += [s, i, pixel[s]]
            s = i
    return arr


def differenz(neu: list[str], alt: list[str]) -> list:
    """Nur die geaenderten Pixel als [index, farbe, index, farbe, ...]."""
    arr: list = []
    for i, farbe in enumerate(neu):
        if farbe != alt[i]:
            arr += [i, farbe]
    return arr
