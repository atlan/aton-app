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

from dataclasses import dataclass, field, replace
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
    # Nur bei diesen Widget-Typen im Formular zeigen. Leer = bei allen.
    #
    # ⚠ Das ist eine Angabe fuer die OBERFLAECHE, keine Pruefregel: `WIDGET_KEYS` bleibt
    # eine flache Menge, und der Loader nimmt `image:` auch an einer Uhr an. Absichtlich
    # so — eine typgebundene Pruefung wuerde jeden Typwechsel zur Sackgasse machen
    # (siehe 0.12.5), und genau das war schon einmal der Fehler.
    nur_typ: list[str] = field(default_factory=list)

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
        if self.nur_typ:
            d["nur_typ"] = self.nur_typ
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
         "Gilt nur, wenn das Tor gar nicht existiert oder unavailable meldet, und nur für "
         "die Frage „an oder aus“. Ohne diesen Rückfall käme der Renderer nach einem "
         "Segmentverlust nie wieder in Gang. Gesendet wird trotzdem erst, wenn das Tor "
         "selbst antwortet — sonst schriebe Aton in die Bootzeit des Geräts hinein"),
    Feld("wartezeit", "int", "Wartezeit auf das Tor",
         "Gesendet wird erst, wenn das Tor „on“ meldet: HA setzt es genau dann, wenn es "
         "mit dem Gerät spricht. So lange wird darauf gewartet, bevor es trotzdem einmal "
         "versucht wird — dieser eine Versuch löst den Segmentverlust auf. Gemessene "
         "Hochläufe lagen zwischen 18 und 95 s",
         vorgabe=90, min=0, max=600, einheit="s"),
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

# Was eine Meldezeile ausmacht — geteilt zwischen dem alten `notify:`-Block und dem
# Widget-Typ `notify`. EINE Liste, damit beide Schreibweisen dieselben Grenzen und
# dieselben Vorgaben haben; zwei Listen wären zwei Wahrheiten.
MELDUNG: list[Feld] = [
    Feld("max_bar_chars", "int", "Balken bis",
         "Längerer Text läuft als WLED-Laufschrift", vorgabe=30, min=1, max=200),
    Feld("max_chars", "int", "Höchstlänge", vorgabe=60, min=1, max=255),
    Feld("scroll_speed", "int", "Lauftempo", vorgabe=128, min=0, max=255),
    Feld("scroll_yoff", "int", "Y-Versatz", "128 = mittig im 8-px-Streifen",
         vorgabe=128, min=0, max=255),
    Feld("scroll_font", "int", "WLED-Schrift", "128 = 6x8", vorgabe=128, min=0, max=255),
]


def _nur(felder: list[Feld], *typen: str) -> list[Feld]:
    """Dieselben Felder, im Formular aber nur bei diesen Widget-Typen."""
    return [replace(f, nur_typ=list(typen)) for f in felder]


# Der alte Block `notify:` je Anzeige. Bleibt erlaubt und wird beim Laden in ein Widget
# übersetzt (config.py) — deshalb steht hier weiterhin `region` statt `at`/`size`.
NOTIFY: list[Feld] = [
    Feld("region", "rechteck", "Bereich", "x, y, Breite, Höhe der Meldezeile", pflicht=True),
    Feld("visible_when", "vorlage", "Sichtbar wenn",
         "Jinja-Bedingung, z.B. nur bei Anwesenheit im Raum"),
    Feld("font", "schrift", "Schrift"),
] + MELDUNG

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
    Feld("page_cycles", "int", "Seiten wechseln alle",
         "Hat der Screen mehrere Seiten, wechseln sie sich ab. 0 = nur die erste. "
         "Ein Zyklus ist ein Bildtakt (interval)",
         vorgabe=0, min=0, max=1000, einheit="Zyklen"),
]

# Eine Seite ist eine Fassung DESSELBEN Screens: in der Auswahl steht weiterhin nur der
# Screen, gewechselt wird innerhalb. Genau das unterscheidet sie von zwei Screens —
# die waeren zwei Stellungen, und eine Handauswahl haette den Wechsel angehalten.
SEITE: list[Feld] = [
    Feld("name", "text", "Name", "Nur zur Orientierung im Konfigurator"),
    Feld("cycles", "int", "Diese Seite steht",
         "Eigene Standzeit nur für diese Seite. 0 = so lange wie im Screen eingestellt. "
         "Damit steht eine Seite länger als die andere",
         vorgabe=0, min=0, max=1000, einheit="Zyklen"),
]

WIDGET_TYPEN = ["tile", "text", "icon", "image", "rect", "calendar", "clock", "clock_wd",
                "notify", "icons", "series", "bar", "lines", "sparkline"]

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
    Feld("image", "symbol", "Bilddatei", "PNG aus /homeassistant/aton_icons",
         nur_typ=["image"]),
    Feld("layer", "int", "Ebene",
         "Höhere Ebene wird später gezeichnet, liegt also oben. Kacheln des Grundbilds "
         "und der Screens stehen auf 0; eine Meldezeile gehört über beide", vorgabe=0,
         min=0, max=9),
    Feld("visible_when", "vorlage", "Sichtbar wenn",
         "Jinja-Bedingung. Trifft sie nicht zu, wird die Kachel übersprungen"),
    Feld("channel", "text", "Kanal",
         "Nur Meldungen dieses Kanals. Leer = Hauptzeile: zeigt alle Meldungen ohne Kanal "
         "— und solche, für deren Kanal es keine Zeile gibt, damit nichts still verschwindet",
         nur_typ=["notify"]),
    Feld("show_levels", "text", "Nur Stufen",
         "Kommaliste, z.B. 'warning'. Leer = alle Stufen", nur_typ=["notify"]),
    Feld("spacing", "int", "Abstand waagerecht",
         "Pixel zwischen zwei Symbolen bzw. Spalten", vorgabe=1,
         min=0, max=32, einheit="px", nur_typ=["icons", "serie"]),
    Feld("line_spacing", "int", "Abstand senkrecht",
         "Pixel zwischen den Reihen: bei `serie` zwischen Beschriftung, Symbol und "
         "Beschriftung, bei `icons` zwischen umgebrochenen Zeilen. Leer = derselbe Wert "
         "wie waagerecht", min=0, max=32, einheit="px", nur_typ=["icons", "serie"]),
    Feld("row_colors", "text", "Farbe je Reihe",
         "Kommaliste, eine Farbe je Reihe: `ffff00, , 30c030`. Leerer Eintrag oder "
         "fehlende Angabe = Farbe der Kachel", nur_typ=["series"]),
    Feld("row_fonts", "text", "Schrift je Reihe",
         "Kommaliste, eine Schrift je Reihe: `, , spleen-5x8`. Leerer Eintrag oder "
         "fehlende Angabe = Schrift der Kachel", nur_typ=["series"]),
    Feld("cell_size", "groesse", "Zellengröße",
         "Feste Breite × Höhe je Symbol bzw. Spalte. Leer = größtes vorkommendes; damit "
         "stehen die Spalten auch bei unterschiedlich breitem Inhalt sauber untereinander",
         nur_typ=["icons", "serie"]),

    # ── Balken und Kurve teilen sich die Skala ──────────────────────────────
    # ★ Absichtlich DIESELBEN Schlüsselnamen für beide Typen: „von wo bis wo" ist dieselbe
    # Frage, und wer den Typ wechselt, soll seine Skala behalten statt sie neu zu tippen.
    #
    # ⚠⚠ Und deshalb NICHT `min`/`max`: diese Namen benutzt das mitgelieferte
    # Beispiel-Plugin `bargraph`, und ein Plugin-Feld, das ein eingebauter Schlüssel
    # belegt, wird beim Laden abgelehnt (seit 0.13.0, mit Absicht — es käme sonst nie beim
    # Plugin an). Die eingebauten Typen hier hätten also jede fremde Datei zerlegt, die
    # `min:` benutzt. Die Tests haben genau das gefangen.
    Feld("scale_min", "float", "Skalenanfang",
         "Leer bei `sparkline` = der kleinste Wert im Zeitraum", vorgabe=0.0,
         nur_typ=["bar", "sparkline"]),
    Feld("scale_max", "float", "Skalenende",
         "Leer bei `sparkline` = der größte Wert im Zeitraum", vorgabe=100.0,
         nur_typ=["bar", "sparkline"]),

    Feld("track", "farbe", "Spurfarbe",
         "Der ungefüllte Teil des Balkens. Leer = gar nicht zeichnen", nur_typ=["bar"]),
    Feld("vertical", "bool", "Senkrecht",
         "Füllt von unten nach oben statt von links nach rechts", nur_typ=["bar"]),

    Feld("hours", "int", "Zeitraum", "Wie weit die Kurve zurückreicht", vorgabe=24,
         min=1, max=168, einheit="h", nur_typ=["sparkline"]),
    Feld("fill", "farbe", "Füllung",
         "Fläche unter der Kurve. Leer = nur die Linie", nur_typ=["sparkline"]),

    Feld("max_rows", "int", "Zeilen höchstens",
         "0 = so viele wie in die Höhe passen", vorgabe=0, min=0, max=64,
         nur_typ=["lines"]),
    Feld("separator", "text", "Trenner",
         "Womit die Textquelle in Zeilen zerfällt. Leer = Zeilenumbruch",
         nur_typ=["lines"]),
] + _nur(MELDUNG, "notify")

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
SCREEN_KEYS = _namen(SCREEN) | {"widgets", "pages"}
SEITE_KEYS = _namen(SEITE) | {"widgets"}
TEXT_KEYS = _namen(TEXTQUELLE)
# `levels` steht nur in der YAML — eine Zuordnung Stufe → zwei Farben lässt sich im
# Formular nicht sinnvoll abbilden, und die Vorgaben (info grün, warning rot) stimmen fast
# immer. Beim `notify:`-Block ist es seit jeher genauso.
WIDGET_KEYS = _namen(WIDGET) | TEXT_KEYS | {"levels"}
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
        "wechsel_s": ("page_cycles",
                      lambda wert, ktx: max(1, round(float(wert) / (ktx.get("interval") or 5)))
                      if float(wert) > 0 else 0),
        # 0.17.0: die letzten deutschen Schluessel wurden englisch — der Rest der
        # Beschreibungssprache war es laengst (type/at/size/template/align/spacing).
        "wechsel_zyklen": ("page_cycles", None),
        "seiten": ("pages", None),
    },
    "seite": {
        "zyklen": ("cycles", None),
    },
}

# Umbenannte WIDGET-TYPEN. Eigene Tabelle, weil ein Typ ein WERT ist und kein Schluessel —
# `UMBENANNT` oben greift nur auf Schluesselnamen.
TYP_UMBENANNT: dict[str, str] = {
    "serie": "series",      # 0.17.0
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


def als_dict(katalog=None, sprache: str = "de", eigene: dict[str, dict] | None = None,
             eigene_fehler: list[str] | None = None) -> dict:
    """Das ganze Schema für die Oberfläche, wahlweise übersetzt.

    Ohne Katalog kommen die deutschen Texte aus dieser Datei — sie sind zugleich die
    Rückfallebene, wenn eine Übersetzung eine Zeichenkette nicht kennt.

    `eigene` sind die geladenen Fremdtypen aus `/config/aton_widgets` (Name → Beschreibung
    samt Feldern). Sie kommen als Parameter herein und nicht über einen Import, damit diese
    Datei weiterhin nichts kennt außer sich selbst — sie ist die Beschreibung der Felder,
    nicht deren Verwaltung. Übersetzt werden sie nicht: ihre Texte stehen in der Datei des
    Benutzers, und ein Katalog dafür wäre ein Katalog ohne Einträge.
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

    alle_typen = WIDGET_TYPEN + sorted(eigene or {})

    # ★★ Das Auswahlfeld `type` baut die Oberfläche aus DIESER Liste, nicht aus dem
    # `widget_typen` unten — `feldBauen` in konfigurator.js nimmt `f.optionen` des Feldes.
    # Ohne diese Zeilen stimmt `widget_typen` zwar, das Klappfeld bleibt aber bei den
    # eingebauten Typen: der eigene Typ ist im Schema vorhanden und trotzdem nicht
    # auswählbar. Genau so passiert, und von außen sah es nach einem Zwischenspeicher aus.
    for f in daten["widget"]:
        if f["name"] == "type":
            f["optionen"] = alle_typen

    daten.update({
        "widget_typen": alle_typen,
        "widget_eigene": eigene or {},
        "widget_eigene_fehler": eigene_fehler or [],
        "icon_formen": ["name", "map", "steps", "template"],
    })
    return daten
