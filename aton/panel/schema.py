"""Beschreibung der YAML-Felder — für den Konfigurator UND für die Prüfung.

★ Warum diese Datei existiert: die Oberfläche des Konfigurators und die Prüfung beim Laden
müssen dieselben Felder kennen. Zwei getrennte Listen laufen garantiert auseinander — dann
bietet der Konfigurator ein Feld an, das der Loader ablehnt, oder umgekehrt. Deshalb steht
die Feldliste **hier**, `config.py` prüft gegen sie, und der Konfigurator baut seine
Formulare daraus.

Die Beschreibung ist bewusst schlicht gehalten: Name, Art, Beschriftung, Hilfetext. Was
sich nicht sinnvoll beschreiben lässt (die vier Formen von `icon`, die Textquellen), wird
in der Oberfläche als eigener Baustein behandelt und ist hier nur als Art vermerkt.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Feld:
    name: str
    art: str                      # siehe ARTEN
    label: str
    hilfe: str = ""
    pflicht: bool = False
    vorgabe: Any = None
    optionen: list[str] = field(default_factory=list)   # nur art="auswahl"
    min: float | None = None
    max: float | None = None
    einheit: str = ""

    def als_dict(self) -> dict:
        d = {"name": self.name, "art": self.art, "label": self.label}
        if self.hilfe:
            d["hilfe"] = self.hilfe
        if self.pflicht:
            d["pflicht"] = True
        if self.vorgabe is not None:
            d["vorgabe"] = self.vorgabe
        if self.optionen:
            d["optionen"] = self.optionen
        for k in ("min", "max"):
            if getattr(self, k) is not None:
                d[k] = getattr(self, k)
        if self.einheit:
            d["einheit"] = self.einheit
        return d


# Arten, die die Oberfläche kennen muss:
#   text int float bool farbe entitaet schrift symbol vorlage format
#   auswahl zelle punkt groesse rechteck textquelle symbolquelle farbquelle
ARTEN = ("text", "int", "float", "bool", "farbe", "entitaet", "schrift", "symbol",
         "vorlage", "format", "auswahl", "zelle", "punkt", "groesse", "rechteck",
         "textquelle", "symbolquelle", "farbquelle")


# ==========================================================================
#  Gruppen
# ==========================================================================
DEFAULTS: list[Feld] = [
    Feld("font", "schrift", "Schrift", "Vorgabe für alle Kacheln", vorgabe="5x3"),
    Feld("color", "farbe", "Farbe", "Vorgabe für Texte", vorgabe="ffffff"),
    Feld("interval", "float", "Takt", "Sekunden zwischen zwei Bildern",
         vorgabe=5.0, min=0.5, max=3600, einheit="s"),
]

SCHRIFT_OPTIONEN: list[Feld] = [
    Feld("uppercase", "bool", "Großschrift",
         "In 5 px sind Kleinbuchstaben unlesbar", vorgabe=False),
    Feld("transliterate", "bool", "Umlaute ersetzen",
         "Ä→AE, Ö→OE, Ü→UE, ß→SS — nötig, wo kein Platz für Punkte ist", vorgabe=False),
]

PANEL: list[Feld] = [
    Feld("id", "text", "Kennung",
         "Wird Teil der Entity-IDs. Nur Buchstaben, Ziffern, '-' und '_'", pflicht=True),
    Feld("name", "text", "Name", "Anzeigename in Home Assistant"),
    Feld("host", "text", "Adresse", "IP oder Hostname des WLED-Geräts", pflicht=True),
    Feld("size", "groesse", "Größe", "Breite × Höhe in Pixeln", pflicht=True),
    Feld("interval", "float", "Takt", "Sekunden zwischen zwei Bildern",
         vorgabe=5.0, min=0.5, max=3600, einheit="s"),
    Feld("full_frame_every", "int", "Vollbild alle",
         "Nach N Bildern ein vollständiges als Wiederaufsetzpunkt",
         vorgabe=60, min=1, max=10000, einheit="Bilder"),
    Feld("dry_run", "bool", "Probelauf",
         "Rechnen und in der Vorschau zeigen, aber NICHTS senden. Nötig, solange ein "
         "zweiter Renderer dieselbe Fläche bedient — zwei Schreiber ergeben Mischbilder",
         vorgabe=False),
    Feld("canvas_segment", "int", "Segment der Bildfläche", vorgabe=0, min=0, max=255),
    Feld("scroll_segment", "int", "Segment der Laufschrift",
         "Muss existieren: HA legt den Hauptschalter nur an, solange das Gerät mehr als "
         "ein Segment hat", vorgabe=1, min=0, max=255),
    Feld("clear_segments_to", "int", "Altsegmente räumen bis",
         "WLEDs MAX_NUM_SEGMENTS, auf ESP32 normalerweise 32", vorgabe=32, min=2, max=255),
    Feld("led_pitch", "float", "LED-Abstand",
         "Rastermaß der Matrix in Millimetern (P3 = 3,0). Wirkt NUR auf die Darstellung: "
         "die Vorschau wird darauf bezogen skaliert — zwei Anzeigen stehen damit im "
         "echten Größenverhältnis — und die LEDs werden als Punkte gezeichnet. "
         "Leer lassen: alles wie bisher",
         min=0.5, max=20, einheit="mm"),
]

GATE: list[Feld] = [
    Feld("entity", "entitaet", "Tor",
         "WLEDs Hauptschalter — der echte Aus-Schalter der Anzeige"),
    Feld("fallback", "entitaet", "Rückfall",
         "Gilt nur, wenn das Tor gar nicht existiert oder unavailable meldet. Ohne diesen "
         "Rückfall käme der Renderer nach einem Segmentverlust nie wieder in Gang"),
    Feld("script", "entitaet", "Schaltskript",
         "Was der An/Aus-Schalter im Betrieb auslöst. Leer = Tor bzw. Rückfall direkt "
         "schalten. Ein Skript ist dort nötig, wo mehr passieren muss als Strom an: "
         "warten bis das Gerät gebootet ist, HAs Konfigurationseintrag aktivieren, "
         "danach ein Vollbild"),
]

BRIGHTNESS: list[Feld] = [
    Feld("entity", "entitaet", "Helligkeit aus",
         "Leer lassen, dann legt die Integration einen eigenen Regler an"),
    Feld("default", "int", "Vorgabe", vorgabe=128, min=1, max=255),
]

GRID: list[Feld] = [
    Feld("row_height", "int", "Zeilenhöhe", vorgabe=9, min=1, max=64, einheit="px"),
    Feld("col_width", "int", "Spaltenbreite", vorgabe=32, min=1, max=256, einheit="px"),
    Feld("icon_width", "int", "Symbolbreite", vorgabe=8, min=0, max=64, einheit="px"),
    Feld("gap", "int", "Abstand", "Zwischen Symbol und Text", vorgabe=1, min=0, max=16,
         einheit="px"),
]

NOTIFY: list[Feld] = [
    Feld("region", "rechteck", "Bereich", "x, y, Breite, Höhe der Meldezeile", pflicht=True),
    Feld("visible_when", "vorlage", "Sichtbar wenn",
         "Jinja-Bedingung, z.B. nur bei Anwesenheit im Raum"),
    Feld("max_bar_chars", "int", "Balken bis",
         "Längerer Text läuft als WLED-Laufschrift", vorgabe=30, min=1, max=200),
    Feld("max_chars", "int", "Höchstlänge", vorgabe=60, min=1, max=255),
    Feld("font", "schrift", "Schrift"),
    Feld("scroll_speed", "int", "Lauftempo", vorgabe=128, min=0, max=255),
    Feld("scroll_yoff", "int", "Y-Versatz", "128 = mittig im 8-px-Streifen",
         vorgabe=128, min=0, max=255),
    Feld("scroll_font", "int", "WLED-Schrift", "128 = 6x8", vorgabe=128, min=0, max=255),
]

SCREEN_GROUP: list[Feld] = [
    Feld("id", "text", "Kennung", "Wird Teil der Entity-ID der Auswahl", pflicht=True),
    Feld("name", "text", "Name", "Beschriftung der Auswahl in Home Assistant"),
    Feld("region", "rechteck", "Bereich",
         "Der Ausschnitt des Bildes, in dem sich der Inhalt austauscht", pflicht=True),
]

SCREEN: list[Feld] = [
    Feld("name", "text", "Name", "Erscheint als Stellung in der Auswahl", pflicht=True),
    Feld("when", "vorlage", "Bedingung",
         "Jinja. Der erste Screen, dessen Bedingung zutrifft, gewinnt. Leer = Rückfall"),
    Feld("wechsel_zyklen", "int", "Seiten wechseln alle",
         "Hat der Screen mehrere Seiten, wechseln sie sich ab. 0 = nur die erste. "
         "Ein Zyklus ist ein Bildtakt (interval)",
         vorgabe=0, min=0, max=1000, einheit="Zyklen"),
]

# Eine Seite ist eine Fassung DESSELBEN Screens: in der Auswahl steht weiterhin nur der
# Screen, gewechselt wird innerhalb. Genau das unterscheidet sie von zwei Screens —
# die waeren zwei Stellungen, und eine Handauswahl haette den Wechsel angehalten.
SEITE: list[Feld] = [
    Feld("name", "text", "Name", "Nur zur Orientierung im Konfigurator"),
    Feld("zyklen", "int", "Diese Seite steht",
         "Eigene Standzeit nur für diese Seite. 0 = so lange wie im Screen eingestellt. "
         "Damit steht eine Seite länger als die andere",
         vorgabe=0, min=0, max=1000, einheit="Zyklen"),
]

WIDGET_TYPEN = ["tile", "text", "icon", "image", "rect", "calendar", "clock"]

WIDGET: list[Feld] = [
    Feld("type", "auswahl", "Typ", vorgabe="tile", optionen=WIDGET_TYPEN),
    Feld("cell", "zelle", "Rasterzelle", "Zeile und Spalte — schließt 'at' aus"),
    Feld("at", "punkt", "Position", "x, y in Pixeln — schließt 'cell' aus"),
    Feld("size", "groesse", "Größe", "Breite × Höhe"),
    Feld("icon", "symbolquelle", "Symbol",
         "Fester Name, oder aus einem Zustand (map / steps) oder einer Vorlage"),
    Feld("color", "farbquelle", "Farbe",
         "Fest oder aus dem Zustand abgeleitet — so wechselt ein Feld die Farbe"),
    Feld("bg", "farbe", "Hintergrund", "Leer = durchsichtig"),
    Feld("font", "schrift", "Schrift"),
    Feld("align", "auswahl", "Ausrichtung", vorgabe="left",
         optionen=["left", "center", "right"]),
    Feld("text_at", "punkt", "Textfeld an", "Eigene Position statt der Rasterposition"),
    Feld("text_width", "int", "Textbreite", einheit="px", min=1, max=1024),
    Feld("image", "symbol", "Bilddatei", "PNG aus /homeassistant/aton_icons"),
]

# Die Textquelle ist ein eigener Baustein: genau eine der drei Quellen, dazu Formatierung.
TEXTQUELLE: list[Feld] = [
    Feld("text", "text", "Fester Text"),
    Feld("value", "entitaet", "Zustand von"),
    Feld("attribute", "text", "Attribut", "Statt des Zustands"),
    Feld("format", "format", "Format", "Python-Format, z.B. {:.1f}°C"),
    Feld("decimals", "int", "Nachkommastellen",
         "Statt Format: runden und nachlaufende Nullen weglassen", min=0, max=10),
    Feld("scale", "float", "Faktor", "Vor der Formatierung multiplizieren", vorgabe=1.0),
    Feld("template", "vorlage", "Vorlage", "Jinja — schlägt alles andere"),
    Feld("unavailable", "text", "Ersatztext", "Wenn der Wert fehlt", vorgabe="--"),
]


# ==========================================================================
#  Schlüsselmengen — von config.py benutzt, damit nichts auseinanderläuft
# ==========================================================================
def _namen(felder: list[Feld]) -> set[str]:
    return {f.name for f in felder}


DEFAULTS_KEYS = _namen(DEFAULTS)
SCHRIFT_KEYS = _namen(SCHRIFT_OPTIONEN)
GATE_KEYS = _namen(GATE)
BRIGHTNESS_KEYS = _namen(BRIGHTNESS)
GRID_KEYS = _namen(GRID)
NOTIFY_KEYS = _namen(NOTIFY) | {"levels"}
SCREEN_GROUP_KEYS = _namen(SCREEN_GROUP) | {"screens"}
SCREEN_KEYS = _namen(SCREEN) | {"widgets", "seiten"}
SEITE_KEYS = _namen(SEITE) | {"widgets"}
TEXT_KEYS = _namen(TEXTQUELLE)
WIDGET_KEYS = _namen(WIDGET) | TEXT_KEYS
PANEL_KEYS = _namen(PANEL) | {"gate", "brightness", "grid", "widgets", "screen_groups",
                              "notify"}
WURZEL_KEYS = {"defaults", "fonts", "panels"}

ICON_KEYS = {"name", "value", "steps", "map", "default", "template"}
LEVEL_KEYS = {"bg", "fg"}


# ==========================================================================
#  Umbenannte Felder
# ==========================================================================
# ★ Warum das hier steht und nicht in einer Migrationsdatei: die Pruefung ist
# absichtlich streng — ein unbekannter Schluessel ist ein Tippfehler und soll laut
# scheitern (`valu` statt `value`). Genau diese Strenge trifft aber auch eine
# UMBENENNUNG, und dann steht der Benutzer vor „unbekannter Schluessel" bei etwas,
# das gestern noch richtig war. Bekannt-veraltete Namen gehoeren deshalb als solche
# aufgeschrieben — dann laesst sich der Wert uebernehmen, statt ihn abzulehnen.
#
# Aufbau: Gruppe -> alter Name -> (neuer Name, Umrechner oder None).
# Der Umrechner bekommt (wert, kontext) und liefert den neuen Wert; `kontext` traegt,
# was die Umrechnung sonst noch braucht (z.B. den Bildtakt der Anzeige).
UMBENANNT: dict[str, dict[str, tuple[str, Any]]] = {
    "screen": {
        # 0.5.16 -> 0.5.17: Sekunden wurden zu Zyklen (ein Zyklus = ein Bildtakt).
        "wechsel_s": ("wechsel_zyklen",
                      lambda wert, ktx: max(1, round(float(wert) / (ktx.get("interval") or 5)))
                      if float(wert) > 0 else 0),
    },
}

# Weggefallene Felder mit Erklaerung. Ein blosses „unbekannter Schluessel" waere hier
# unfreundlich: der Name war richtig, er steht nur nicht mehr an dieser Stelle.
ENTFERNT: dict[str, dict[str, str]] = {
    "screen_group": {
        "wechsel_zyklen":
            "gehoert seit 0.6.0 an den SCREEN, nicht an die Gruppe: mehrere Screens waren "
            "mehrere Stellungen in der Auswahl, und eine Handauswahl hielt den Wechsel an. "
            "Jetzt bekommt EIN Screen mehrere `seiten:` und `wechsel_zyklen:`",
    },
}


GRUPPEN = {
    "defaults": DEFAULTS, "schrift_optionen": SCHRIFT_OPTIONEN, "panel": PANEL,
    "gate": GATE, "brightness": BRIGHTNESS, "grid": GRID, "notify": NOTIFY,
    "screen_group": SCREEN_GROUP, "screen": SCREEN, "seite": SEITE, "widget": WIDGET,
    "textquelle": TEXTQUELLE,
}


def als_dict(katalog=None, sprache: str = "de") -> dict:
    """Das ganze Schema für die Oberfläche, wahlweise übersetzt.

    Ohne Katalog kommen die deutschen Texte aus dieser Datei — sie sind zugleich die
    Rückfallebene, wenn eine Übersetzung eine Zeichenkette nicht kennt.
    """
    def uebersetzt(gruppe: str, f: Feld) -> dict:
        d = f.als_dict()
        if katalog is not None:
            for teil in ("label", "hilfe"):
                schluessel = f"schema.{gruppe}.{f.name}.{teil}"
                wert = katalog.text(schluessel, sprache)
                if wert != schluessel:
                    d[teil] = wert
        return d

    daten = {gruppe: [uebersetzt(gruppe, f) for f in felder]
             for gruppe, felder in GRUPPEN.items()}
    daten.update({
        "widget_typen": WIDGET_TYPEN,
        "icon_formen": ["name", "map", "steps", "template"],
    })
    return daten
