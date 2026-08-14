"""Eigene Widget-Typen — Python-Dateien aus `/config/aton_widgets`.

★ Warum es diese Datei gibt: die eingebauten Typen decken ab, was sich sinnvoll in YAML
beschreiben laesst — Kachel, Text, Symbol, Uhr. Alles, was RECHNET, laesst sich so nicht
ausdruecken: ein Balken, ein Ring, ein Zeiger, eine eigene Umrechnung. Statt fuer jeden
Sonderfall einen Typ in den Renderer zu schreiben, bringt der Benutzer ihn selbst mit.

Ein Plugin meldet dabei nicht nur eine Zeichenfunktion an, sondern auch **seine Felder**.
Das ist der ganze Trick: aus derselben Feldliste zieht die Pruefung beim Laden ihre
erlaubten Schluessel UND der Konfigurator sein Eingabeformular. Ein Plugin fuehlt sich
dadurch an wie ein eingebauter Typ — mit Fehlermeldung bei Tippfehlern statt mit einem
durchgereichten Dictionary, in dem `ours: 24` still danebengeht.

⚠ Hier laeuft fremder Python-Code im Add-on-Container. Deshalb liest `lade()` das
Verzeichnis nur, wenn die Add-on-Option `custom_widgets` gesetzt ist — wer sie nicht
bewusst umlegt, fuehrt auch nichts aus.

Eine Datei sieht so aus:

    from aton_api import Feld, widget

    @widget("bargraph", felder=[
        Feld("sensor", "entitaet", "Sensor", pflicht=True),
        Feld("max", "float", "Vollausschlag", vorgabe=100.0),
    ])
    def zeichne(bild, w, ctx):
        anteil = (ctx.zahl(w.optionen["sensor"]) or 0) / w.optionen["max"]
        ...
"""
from __future__ import annotations

import glob
import importlib.util
import logging
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from PIL import Image, ImageDraw

from .const import DEFAULT_COLOR, USER_WIDGET_DIR, anzeige_pfad
from .icons import _hex2rgb
from .schema import WIDGET_KEYS, WIDGET_TYPEN, Feld

_LOG = logging.getLogger(__name__)

# Der Typname wird Teil der YAML und der Fehlermeldungen — knapp und ohne Ueberraschungen.
NAME_ERLAUBT = re.compile(r"^[a-z][a-z0-9_]{0,31}$")

# ★ Nur skalare Arten. Die zusammengesetzten (`zelle`, `punkt`, `groesse`, `rechteck`,
# `textquelle`, `symbolquelle`, `farbquelle`) sind in der Oberflaeche eigene Bausteine und
# tragen im Loader eigene Umrechnungen — die einem Plugin mitzugeben hiesse, die halbe
# Pruefung zu veroeffentlichen. Wer eine Position braucht, nimmt zwei `int`-Felder.
ERLAUBTE_ARTEN = frozenset({"text", "int", "float", "bool", "farbe", "entitaet",
                            "schrift", "symbol", "vorlage", "format", "auswahl"})


# ★★ Unter DIESEM Namen importieren Plugins die Schnittstelle — nicht als `panel.plugin`.
# Wie das Paket der App heisst, ist Innensache und hat schon zweimal gewechselt: im
# Container laeuft sie als `panel` (PYTHONPATH=/opt/aton, `python3 -m panel`), im Baum
# liegt sie unter `aton/panel`. Stuende der echte Pfad in den Dateien des Benutzers, waere
# jede Umbenennung hier ein Fehler in fremden Dateien, die niemand mitzieht.
sys.modules.setdefault("aton_api", sys.modules[__name__])


class PluginError(Exception):
    """Ein Plugin meldet etwas an, das so nicht geht — beim Laden, nicht beim Zeichnen."""


# ==========================================================================
#  Was ein Plugin anmeldet
# ==========================================================================
@dataclass
class EigenerTyp:
    name: str
    zeichne: Callable[[Image.Image, Any, "Kontext"], None]
    felder: list[Feld] = field(default_factory=list)
    beschreibung: str = ""
    quelle: str = "?"                     # Datei, aus der er stammt — fuer Fehlermeldungen

    @property
    def schluessel(self) -> set[str]:
        return {f.name for f in self.felder}

    @property
    def entitaets_felder(self) -> list[str]:
        """Felder der Art `entitaet`.

        ⚠ Die sind nicht nur Deko: aus ihnen wird `Widget.entities` gefuellt, und DARAUS
        wiederum die Liste der Zustaende, die die App bei Home Assistant abonniert. Ein
        Plugin, dessen Entitaet hier fehlt, wird nie neu gezeichnet — es steht still, ohne
        dass irgendwo ein Fehler auftaucht.
        """
        return [f.name for f in self.felder if f.art == "entitaet"]

    def als_dict(self) -> dict:
        return {"name": self.name, "beschreibung": self.beschreibung,
                "quelle": self.quelle, "felder": [f.als_dict() for f in self.felder]}


# Der Dekorator laeuft waehrend `exec_module`, die Registrierung muss also irgendwo
# zwischengelagert werden. `lade()` leert die Liste vor jeder Datei und raeumt sie danach
# ab — damit ist auch klar, welche Anmeldung aus welcher Datei kam.
_SAMMLUNG: list[EigenerTyp] = []


def widget(name: str, felder: list[Feld] | None = None, beschreibung: str = ""):
    """Eine Zeichenfunktion als Widget-Typ anmelden.

    Die Funktion bekommt `(bild, w, ctx)`: das Bild der Anzeige (PIL, RGBA), das Widget
    mit Lage (`w.x`, `w.y`, `w.w`, `w.h`) und den geprueften eigenen Werten in
    `w.optionen`, sowie den Kontext fuer Zustaende, Schriften und Symbole.
    """
    def nimm(fn: Callable) -> Callable:
        typ = EigenerTyp(name=str(name), zeichne=fn, felder=list(felder or []),
                         beschreibung=beschreibung)
        _pruefe(typ)
        _SAMMLUNG.append(typ)
        return fn
    return nimm


def _pruefe(typ: EigenerTyp) -> None:
    if not NAME_ERLAUBT.match(typ.name):
        raise PluginError(f"Typname {typ.name!r} nicht erlaubt — "
                          "Kleinbuchstaben, Ziffern und '_', beginnend mit einem Buchstaben")
    if typ.name in WIDGET_TYPEN:
        raise PluginError(f"Typname {typ.name!r} ist schon eingebaut — bitte anders nennen")
    if not callable(typ.zeichne):
        raise PluginError(f"{typ.name}: die Zeichenfunktion ist nicht aufrufbar")

    gesehen: set[str] = set()
    for f in typ.felder:
        if not isinstance(f, Feld):
            raise PluginError(f"{typ.name}: 'felder' nimmt nur Feld-Objekte, nicht {f!r}")
        if f.art not in ERLAUBTE_ARTEN:
            raise PluginError(f"{typ.name}.{f.name}: Art {f.art!r} geht hier nicht — "
                              f"erlaubt: {', '.join(sorted(ERLAUBTE_ARTEN))}")
        # ★ Ein Feld, das genauso heisst wie ein eingebauter Schluessel, wuerde nie beim
        # Plugin ankommen: `_widget` in config.py wertet `color`, `font`, `value` … selbst
        # aus. Das faellt sonst erst auf, wenn das Widget hartnaeckig den falschen Wert
        # zeichnet — also hier abfangen, wo noch ein Dateiname dabeisteht.
        if f.name in WIDGET_KEYS:
            raise PluginError(f"{typ.name}.{f.name}: Feldname ist schon vom eingebauten "
                              "Schema belegt und kaeme nie beim Plugin an")
        if f.name in gesehen:
            raise PluginError(f"{typ.name}.{f.name}: Feldname doppelt")
        if f.art == "auswahl" and not f.optionen:
            raise PluginError(f"{typ.name}.{f.name}: Art 'auswahl' braucht 'optionen'")
        gesehen.add(f.name)


# ==========================================================================
#  Verwaltung
# ==========================================================================
class WidgetRegistry:
    """Die geladenen eigenen Typen. Eine Instanz je Prozess (`registry` unten)."""

    def __init__(self) -> None:
        self._typen: dict[str, EigenerTyp] = {}
        self.fehler: list[str] = []
        self.aktiv = False
        self.verzeichnis = USER_WIDGET_DIR

    def get(self, name: str) -> EigenerTyp | None:
        return self._typen.get(name)

    def namen(self) -> list[str]:
        return sorted(self._typen)

    def alle(self) -> list[EigenerTyp]:
        return [self._typen[n] for n in sorted(self._typen)]

    def typ_von_schluessel(self, name: str) -> str | None:
        """Welcher eigene Typ hat ein Feld dieses Namens angemeldet?

        Nur fuer Fehlermeldungen: ein Schluessel, der nach einem Typwechsel stehenblieb,
        soll sagen, wo er herkommt — sonst sucht man einen Tippfehler, den es nicht gibt.
        """
        for typ in self.alle():
            if name in typ.schluessel:
                return typ.name
        return None

    def als_dict(self) -> dict[str, dict]:
        return {n: t.als_dict() for n, t in sorted(self._typen.items())}

    def lade(self, aktiv: bool, verzeichnis: str | None = None) -> None:
        """Verzeichnis einlesen. Ersetzt den bisherigen Bestand vollstaendig.

        ⚠ Wird beim Start UND bei „Neu laden" gerufen — aus demselben Grund, aus dem dort
        auch Schriften und Symbole neu aufgebaut werden: sonst bleibt eine geaenderte
        Plugin-Datei unsichtbar, bis jemand die ganze App neu startet, und niemand haette
        geraten, dass ausgerechnet das noetig ist.
        """
        self._typen.clear()
        self.fehler.clear()
        self.aktiv = bool(aktiv)
        if verzeichnis is not None:
            self.verzeichnis = verzeichnis
        if not self.aktiv:
            return
        if not os.path.isdir(self.verzeichnis):
            return
        for pfad in sorted(glob.glob(os.path.join(self.verzeichnis, "*.py"))):
            if os.path.basename(pfad).startswith("_"):
                continue
            self._datei(pfad)

    def _melde(self, pfad: str, text: str) -> None:
        meldung = f"{anzeige_pfad(pfad)}: {text}"
        self.fehler.append(meldung)
        _LOG.error("Eigenes Widget nicht geladen — %s", meldung)

    def _datei(self, pfad: str) -> None:
        _SAMMLUNG.clear()
        name = "aton_widget_" + os.path.splitext(os.path.basename(pfad))[0]
        try:
            spec = importlib.util.spec_from_file_location(name, pfad)
            if spec is None or spec.loader is None:
                self._melde(pfad, "laesst sich nicht als Modul lesen")
                return
            modul = importlib.util.module_from_spec(spec)
            # Vor dem Ausfuehren eintragen: dataclasses und typing schlagen waehrend des
            # Imports in sys.modules nach, und Rueckverfolgungen zeigen sonst keine Zeilen.
            sys.modules[name] = modul
            spec.loader.exec_module(modul)
        except Exception as e:                     # noqa: BLE001 — fremder Code, alles moeglich
            sys.modules.pop(name, None)
            self._melde(pfad, f"{type(e).__name__}: {e}")
            _LOG.debug("Rueckverfolgung", exc_info=True)
            _SAMMLUNG.clear()
            return

        neu, _SAMMLUNG[:] = list(_SAMMLUNG), []
        if not neu:
            self._melde(pfad, "meldet keinen Typ an — fehlt der @widget-Dekorator?")
            return
        for typ in neu:
            if typ.name in self._typen:
                self._melde(pfad, f"Typ {typ.name!r} gibt es schon "
                                  f"(aus {self._typen[typ.name].quelle})")
                continue
            typ.quelle = anzeige_pfad(pfad)
            self._typen[typ.name] = typ
            _LOG.info("Eigenes Widget: %s aus %s (%d Feld(er))",
                      typ.name, typ.quelle, len(typ.felder))


registry = WidgetRegistry()


# ==========================================================================
#  Was ein Plugin vom Renderer benutzen darf
# ==========================================================================
class Kontext:
    """Schmale Fassade auf den Renderer.

    ★ Warum nicht einfach der Renderer selbst: alles, was ein Plugin anfassen kann, ist
    von da an festgelegt — eine Umbenennung im Renderer wuerde fremde Dateien zerlegen,
    die niemand hier im Baum sieht. Diese Klasse ist deshalb die Grenze: sie darf wachsen,
    aber was drin ist, bleibt.
    """

    def __init__(self, renderer) -> None:
        self._r = renderer
        self.panel = renderer.panel

    # --- Zustaende --------------------------------------------------------
    def state(self, entity_id: str) -> str | None:
        """Zustand als Zeichenkette, oder None."""
        return self._r.quelle.state(entity_id)

    def attr(self, entity_id: str, name: str) -> Any:
        return self._r.quelle.attr(entity_id, name)

    def zahl(self, entity_id: str, attribut: str | None = None) -> float | None:
        """Zustand als Zahl — None bei `unknown`, `unavailable` und allem Untauglichen."""
        return self._r._zahl(entity_id, attribut)

    def vorlage(self, text: str) -> str:
        """Eine Jinja2-Vorlage auswerten, wie `template:` in der YAML."""
        return self._r.tmpl.render(text)

    # --- Zeichnen ---------------------------------------------------------
    def rgb(self, farbe: str) -> tuple[int, int, int]:
        """'ff8800' oder 'f80' zu (r, g, b)."""
        return _hex2rgb(farbe)

    def schrift(self, name: str | None = None):
        """Schrift mit `.measure(text)` und `.draw(draw, (x, y), text, rgb)`."""
        return self._r.fonts.get(name)

    def symbol(self, bild: Image.Image, name: str, x: int, y: int) -> None:
        """Ein Symbol aus `aton_icons` (oder ein mitgeliefertes) einsetzen."""
        self._r._symbol(bild, name, x, y)

    def schreibe(self, bild: Image.Image, text: str, x: int, y: int, breite: int,
                 hoehe: int, farbe: str = DEFAULT_COLOR, schrift: str | None = None,
                 align: str = "left") -> None:
        """Text in ein Feld schreiben — abgeschnitten, was nicht hineinpasst."""
        self._r._schreibe(bild, text, x, y, breite, hoehe, farbe, schrift, align)

    def zeichner(self, bild: Image.Image) -> ImageDraw.ImageDraw:
        """PILs `ImageDraw` fuer alles, was Pixel, Linien und Rechtecke braucht."""
        return ImageDraw.Draw(bild)
