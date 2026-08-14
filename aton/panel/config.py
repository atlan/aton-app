"""YAML-Beschreibung einlesen und pruefen.

Bewusst von Hand geprueft statt mit einer Schema-Bibliothek: die Fehlermeldung soll den
**Pfad in der Datei** nennen (`panels[0].screen_groups[1].screens[0].widgets[3].icon`) und
sagen, was stattdessen erlaubt gewesen waere. Eine falsch geschriebene Sensor-ID faellt so
beim Start auf und nicht als leere Kachel auf der Matrix.
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from . import plugin, schema
from .const import DEFAULT_COLOR, DEFAULT_FONT, DEFAULT_INTERVAL

_LOG = logging.getLogger("panel.config")


class ConfigError(Exception):
    """Fehler in der YAML-Beschreibung, mit Pfad."""

    def __init__(self, pfad: str, meldung: str):
        self.pfad = pfad
        super().__init__(f"{pfad}: {meldung}")


# ==========================================================================
#  Bausteine
# ==========================================================================
@dataclass
class TextSpec:
    """Woher der Text einer Kachel kommt."""
    literal: str | None = None
    entity: str | None = None
    attribute: str | None = None
    format: str | None = None          # Python-Format, z.B. "{:.1f}°C"
    decimals: int | None = None        # str(round(wert, n)) — wie der alte Renderer
    scale: float = 1.0
    template: str | None = None        # Jinja
    unavailable: str = "--"

    @property
    def entities(self) -> set[str]:
        return {self.entity} if self.entity else set()


@dataclass
class IconSpec:
    """Welches Symbol gezeichnet wird."""
    name: str | None = None
    entity: str | None = None
    steps: list[tuple[float, str]] = field(default_factory=list)   # (Schwelle, Symbol), absteigend
    map: dict[str, str] = field(default_factory=dict)              # Zustand -> Symbol
    default: str | None = None
    template: str | None = None

    @property
    def entities(self) -> set[str]:
        return {self.entity} if self.entity else set()


@dataclass
class Widget:
    type: str = "tile"
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 8
    icon: IconSpec | None = None
    text: TextSpec | None = None
    text_x: int | None = None
    text_y: int | None = None
    text_w: int | None = None
    color: str | IconSpec = DEFAULT_COLOR      # fest oder aus dem Zustand abgeleitet
    bg: str | None = None
    font: str = DEFAULT_FONT
    align: str = "left"
    # nur type=image
    image: str | None = None
    # Zeichenebene. Alles steht auf 0 und wird in Listenreihenfolge gezeichnet; wer hoeher
    # steht, kommt spaeter dran und liegt damit oben. Braucht vor allem die Meldezeile:
    # sie muss ueber den Screen-Gruppen liegen, egal in welcher Liste sie steht.
    layer: int = 0
    # Jinja-Bedingung. Trifft sie nicht zu, wird die Kachel uebersprungen.
    visible_when: str | None = None
    # nur type=notify
    notify: NotifyCfg | None = None
    # nur type=icons/serie: Abstand zwischen zwei Symbolen und feste Zellengroesse.
    # `line_spacing = None` heisst „wie spacing" — der Renderer setzt das ein.
    spacing: int = 1
    line_spacing: int | None = None
    # nur type=series: Farbe/Schrift je Reihe. Leerer Eintrag = die der Kachel.
    row_colors: list[str] = field(default_factory=list)
    row_fonts: list[str] = field(default_factory=list)
    cell_w: int | None = None
    cell_h: int | None = None
    # Balken und Kurve: None heisst „nicht gesetzt" und bedeutet je Typ etwas anderes —
    # siehe die Begruendung beim Einlesen.
    skala_min: float | None = None
    skala_max: float | None = None
    track: str | None = None
    vertical: bool = False
    hours: int = 24
    fill: str | None = None
    max_rows: int = 0
    separator: str = "\n"
    # nur type=notify: das WLED-Segment, auf dem DIESE Zeile ihre Laufschrift laufen
    # laesst. Beim Einlesen fest vergeben — siehe `_scroll_segmente`.
    scroll_segment: int = 1
    # nur eigene Typen aus /config/aton_widgets: die geprueften Werte der Felder, die das
    # Plugin selbst angemeldet hat. Bei eingebauten Typen immer leer.
    optionen: dict[str, Any] = field(default_factory=dict)
    # Welche davon Entitaeten sind — beim Einlesen einmal ausgerechnet, damit `entities`
    # ohne Rueckgriff auf die Registry auskommt (der Loader kennt den Typ, das Widget nicht).
    optionen_entitaeten: set[str] = field(default_factory=set)
    pfad: str = "?"
    # Wurde die Lage ueber `cell` angegeben? Das entscheidet, ob Verschieben im
    # Konfigurator am Raster einrastet oder pixelweise geht.
    cell_benutzt: bool = False

    @property
    def entities(self) -> set[str]:
        e: set[str] = set()
        if self.icon:
            e |= self.icon.entities
        if self.text:
            e |= self.text.entities
        if isinstance(self.color, IconSpec):
            e |= self.color.entities
        for name in self.optionen_entitaeten:
            wert = self.optionen.get(name)
            if wert:
                e.add(str(wert))
        return e


@dataclass
class Seite:
    """Eine Fassung eines Screens. In der Auswahl steht weiterhin nur der SCREEN."""
    name: str
    widgets: list[Widget] = field(default_factory=list)
    # 0 = so lange wie im Screen eingestellt. Damit stehen ungleiche Standzeiten zur
    # Verfuegung ("Uebersicht 2 Zyklen, Details 1"), ohne dass eine bestehende
    # Beschreibung etwas davon wissen muss.
    zyklen: int = 0


@dataclass
class Screen:
    name: str
    when: str | None = None            # Jinja; None/"always" = Rueckfall
    # ★ Immer gefuellt: eine Beschreibung mit `widgets:` statt `seiten:` bekommt eine
    # einzige Seite. So muss der Renderer nicht zwei Faelle kennen — und ein Screen mit
    # einer Seite verhaelt sich exakt wie frueher.
    seiten: list[Seite] = field(default_factory=list)
    wechsel_zyklen: int = 0

    @property
    def widgets(self) -> list[Widget]:
        """Die Kacheln der ersten Seite — fuer alles, was nur EINE Fassung kennt."""
        return self.seiten[0].widgets if self.seiten else []


@dataclass
class ScreenGroup:
    id: str
    name: str
    region: tuple[int, int, int, int]  # x, y, w, h
    screens: list[Screen] = field(default_factory=list)


@dataclass
class NotifyCfg:
    """Eine Meldezeile. Steht am Widget `type: notify` — und am alten Block `notify:`.

    ★ Der Block ist seit 0.13.0 nur noch eine Schreibweise: `_panel` uebersetzt ihn in ein
    Widget mit `layer: 1`. Deshalb traegt diese Klasse beides — `region` benutzt nur der
    Block, Lage und Groesse des Widgets stehen wie bei jeder Kachel in `at`/`size`.
    """
    region: tuple[int, int, int, int] | None = None
    visible_when: str | None = None
    max_bar_chars: int = 30
    max_chars: int = 60
    font: str = DEFAULT_FONT
    levels: dict[str, tuple[str, str]] = field(
        default_factory=lambda: {"info": ("00c000", "ffffff"), "warning": ("c00000", "ffffff")})
    scroll_fx: int = 122
    scroll_speed: int = 128
    scroll_yoff: int = 128
    scroll_font: int = 128
    # Welche Meldungen diese Zeile zeigt. `channel=None` ist die Hauptzeile.
    channel: str | None = None
    show_levels: set[str] = field(default_factory=set)   # leer = alle


@dataclass
class Grid:
    row_height: int = 9
    col_width: int = 32
    icon_width: int = 8
    gap: int = 1


@dataclass
class PanelCfg:
    id: str
    name: str
    host: str
    width: int
    height: int
    interval: float = DEFAULT_INTERVAL
    full_frame_every: int = 60
    # Probelauf: rechnen und in der Vorschau zeigen, aber NICHTS an WLED schicken.
    # Genau dafuer gedacht, neben einem noch laufenden anderen Renderer zu pruefen —
    # zwei Schreiber auf derselben Flaeche ergeben Mischbilder.
    dry_run: bool = False
    canvas_segment: int = 0
    scroll_segment: int = 1
    clear_segments_to: int = 32   # WLEDs MAX_NUM_SEGMENTS auf ESP32

    @property
    def hoechstes_scroll_segment(self) -> int:
        """Das oberste von den Meldezeilen belegte Segment.

        Darueber darf `clear_segments_to` aufraeumen, darunter nicht — sonst loeschte
        jedes Vollbild die zweite Laufschrift.
        """
        zeilen = [w for w in self.alle_widgets() if w.type == "notify"]
        return max([w.scroll_segment for w in zeilen], default=self.scroll_segment)
    # Rastermass der Matrix in Millimetern (P3 = 3.0). Rein fuer die DARSTELLUNG:
    # bezieht den Zoom der Vorschau darauf und zeichnet die LEDs als Punkte. Auf das,
    # was an WLED geht, hat es keinen Einfluss.
    led_pitch: float | None = None
    gate_entity: str | None = None
    gate_fallback: str | None = None
    gate_script: str | None = None
    #: Wie lange auf ein `on` des Tors gewartet wird, bevor trotzdem einmal gesendet
    #: wird. Siehe `display.NOTAUSGANG_S` — dort steht, warum es diesen Notausgang gibt.
    gate_wartezeit: int = 90
    brightness_entity: str | None = None
    brightness_default: int = 128
    grid: Grid = field(default_factory=Grid)
    widgets: list[Widget] = field(default_factory=list)
    groups: list[ScreenGroup] = field(default_factory=list)
    notify: NotifyCfg = field(default_factory=NotifyCfg)
    # Aus dem alten `notify:`-Block erzeugte Kacheln. Sie stehen BEWUSST nicht in
    # `widgets`: dort zaehlt der Listenindex als Pfad in die YAML-Datei
    # (`panels[0].widgets[3]`), und ein Eintrag ohne Entsprechung in der Datei wuerde den
    # Konfigurator auf eine Kachel zeigen lassen, die es dort gar nicht gibt.
    overlays: list[Widget] = field(default_factory=list)

    @property
    def meldezeilen(self) -> list[Widget]:
        """Alle Meldezeilen der Anzeige — aus dem Grundbild, den Screens und dem Block."""
        return [w for w in self.alle_widgets() if w.type == "notify"]

    def alle_widgets(self) -> list[Widget]:
        """Jede Kachel der Anzeige, unabhaengig davon, welcher Screen gerade laeuft."""
        alle = list(self.widgets)
        for g in self.groups:
            for s in g.screens:
                for seite in s.seiten:
                    alle.extend(seite.widgets)
        alle.extend(self.overlays)
        return alle

    @property
    def notify_levels(self) -> set[str]:
        """Stufen, die `aton.notify` annimmt — die Vereinigung ueber alle Meldezeilen.

        ⚠ Nicht die Stufen EINER Zeile: eine Meldung darf eine Stufe tragen, die nur eine
        zweite Zeile kennt. Ohne Meldezeile bleiben die eingebauten beiden uebrig, sonst
        laesse sich an eine noch nicht eingerichtete Anzeige gar nichts schicken.
        """
        stufen: set[str] = set()
        for w in self.meldezeilen:
            if w.notify:
                stufen |= set(w.notify.levels)
        return stufen or {"info", "warning"}

    @property
    def entities(self) -> set[str]:
        e: set[str] = set()
        for w in self.widgets:
            e |= w.entities
        for g in self.groups:
            for s in g.screens:
                for w in s.widgets:
                    e |= w.entities
        for eid in (self.gate_entity, self.gate_fallback, self.brightness_entity):
            if eid:
                e.add(eid)
        return e


@dataclass
class AppCfg:
    panels: list[PanelCfg] = field(default_factory=list)
    fonts: dict[str, dict] = field(default_factory=dict)
    quelle: str = "?"


# ==========================================================================
#  Pruefhelfer
# ==========================================================================
def _dict(wert: Any, pfad: str) -> dict:
    if not isinstance(wert, dict):
        raise ConfigError(pfad, f"muss eine Zuordnung sein, ist {type(wert).__name__}")
    return wert


def _liste(wert: Any, pfad: str) -> list:
    if not isinstance(wert, list):
        raise ConfigError(pfad, f"muss eine Liste sein, ist {type(wert).__name__}")
    return wert


def _pflicht(d: dict, schluessel: str, pfad: str) -> Any:
    if schluessel not in d:
        raise ConfigError(pfad, f"'{schluessel}' fehlt")
    wert = d[schluessel]
    # ★ Ein LEERES Pflichtfeld ist schlimmer als ein fehlendes: es kommt durch die
    # Pruefung und faellt erst im Betrieb auf — `host: ''` ergaebe Anfragen an
    # `http:///json/state`. Der Konfigurator legt eine neue Anzeige bewusst mit leerem
    # `host` an, damit niemand eine erfundene Adresse geschenkt bekommt; dann muss die
    # Pruefung das hier auch abfangen.
    if isinstance(wert, str) and not wert.strip():
        raise ConfigError(pfad, f"'{schluessel}' ist leer")
    return wert


def _int(wert: Any, pfad: str) -> int:
    try:
        return int(wert)
    except (TypeError, ValueError):
        raise ConfigError(pfad, f"muss eine ganze Zahl sein, ist {wert!r}") from None


def _float(wert: Any, pfad: str) -> float:
    """Wie `_int`, nur mit Komma.

    ⚠ Vorher wurde an mehreren Stellen roh `float(...)` gerufen. Ein Tippfehler in der
    Datei ergab dann einen nackten `ValueError` mitsamt Ablaufverfolgung — statt der
    Meldung mit Pfad, fuer die dieses Modul ueberhaupt von Hand prueft.
    """
    try:
        return float(wert)
    except (TypeError, ValueError):
        raise ConfigError(pfad, f"muss eine Zahl sein, ist {wert!r}") from None


def _umbenannt(d: dict, gruppe: str, pfad: str, **kontext) -> dict:
    """Veraltete Feldnamen auf die aktuellen umschreiben — VOR der Pruefung.

    ★ Die Pruefung auf unbekannte Schluessel ist absichtlich streng: `valu` statt `value`
    soll laut scheitern, nicht still wirkungslos bleiben. Dieselbe Strenge trifft aber
    auch eine UMBENENNUNG — und dann steht man vor „unbekannter Schluessel" bei etwas,
    das gestern noch richtig war, obwohl der Wille voellig klar ist.

    ⚠ Es wird eine KOPIE zurueckgegeben, das Original bleibt unangetastet: der
    Konfigurator arbeitet auf derselben Struktur weiter und wuerde sonst beim naechsten
    Speichern eine Aenderung schreiben, die niemand angefordert hat.
    """
    tabelle = schema.UMBENANNT.get(gruppe, {})
    treffer = [k for k in tabelle if k in d]
    if not treffer:
        return d
    d = dict(d)
    for alt in treffer:
        neu_name, umrechner = tabelle[alt]
        wert = d.pop(alt)
        if neu_name in d:
            # Beide da: der neue Name gilt, der alte wird nur weggeraeumt. Alles andere
            # waere eine stille Entscheidung darueber, was der Benutzer gemeint hat.
            _LOG.warning("%s: %r ist veraltet und wird ignoriert, %r ist gesetzt",
                         pfad, alt, neu_name)
            continue
        try:
            d[neu_name] = umrechner(wert, kontext) if umrechner else wert
        except (TypeError, ValueError) as e:
            raise ConfigError(pfad, f"{alt!r} (veraltet) laesst sich nicht nach "
                                    f"{neu_name!r} uebernehmen: {e}")
        # ⚠ Den Wert nur ANDEUTEN. Bei `wechsel_s` war er eine Zahl, seit 0.17.0 faellt
        # auch `seiten:` hierher — und das ist die komplette Seitenliste mit allen
        # Kacheln. Ausgeschrieben stand danach eine Bildschirmseite YAML im Protokoll,
        # in der die eigentliche Meldung unterging.
        wert = d[neu_name]
        kurz = (f"{len(wert)} Eintraege" if isinstance(wert, (list, dict))
                else repr(wert)[:60])
        _LOG.warning("%s: %r heisst jetzt %r (%s uebernommen) — beim naechsten "
                     "Speichern im Konfigurator wird es umgeschrieben",
                     pfad, alt, neu_name, kurz)
    return d


def _entfernt(d: dict, gruppe: str, pfad: str) -> None:
    """Weggefallene Felder mit Begruendung ablehnen.

    „Unbekannter Schluessel" waere hier unfreundlich und irrefuehrend: der Name war
    richtig, er steht nur nicht mehr an dieser Stelle. Wer das liest, soll wissen, wohin
    er umziehen muss — nicht raten, ob er sich vertippt hat.
    """
    for name, grund in schema.ENTFERNT.get(gruppe, {}).items():
        if name in d:
            raise ConfigError(pfad, f"{name!r} gibt es hier nicht mehr — {grund}")


def _unbekannt(d: dict, erlaubt: set[str], pfad: str) -> None:
    ueber = set(d) - erlaubt
    if ueber:
        raise ConfigError(pfad, "unbekannte Schluessel: " + ", ".join(sorted(ueber))
                          + " — erlaubt sind: " + ", ".join(sorted(erlaubt)))


def _farbe(wert: Any, pfad: str) -> str:
    s = str(wert).lstrip("#").lower()
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or any(c not in "0123456789abcdef" for c in s):
        raise ConfigError(pfad, f"keine Farbe: {wert!r} (erwartet 'rrggbb')")
    return s


def _rechteck(wert: Any, pfad: str) -> tuple[int, int, int, int]:
    lst = _liste(wert, pfad)
    if len(lst) != 4:
        raise ConfigError(pfad, "muss [x, y, breite, hoehe] sein")
    return tuple(_int(v, f"{pfad}[{i}]") for i, v in enumerate(lst))  # type: ignore[return-value]


# ==========================================================================
#  Einlesen
# ==========================================================================
# ★ Die Schluesselmengen stehen in schema.py — dieselbe Quelle, aus der der
# Konfigurator seine Formulare baut. Zwei getrennte Listen liefen garantiert
# auseinander, und dann boete die Oberflaeche Felder an, die hier abgelehnt werden.
TEXT_SCHLUESSEL = schema.TEXT_KEYS


def _text_spec(quelle: dict, pfad: str) -> TextSpec | None:
    vorhanden = TEXT_SCHLUESSEL & set(quelle)
    if not vorhanden:
        return None
    spec = TextSpec(
        literal=quelle.get("text"),
        entity=quelle.get("value"),
        attribute=quelle.get("attribute"),
        format=quelle.get("format"),
        decimals=_int(quelle["decimals"], f"{pfad}.decimals") if "decimals" in quelle else None,
        scale=float(quelle.get("scale", 1.0)),
        template=quelle.get("template"),
        unavailable=str(quelle.get("unavailable", "--")),
    )
    if spec.literal is None and spec.entity is None and spec.template is None:
        raise ConfigError(pfad, "Text braucht eine Quelle: 'text', 'value' oder 'template'")
    if spec.format and spec.decimals is not None:
        raise ConfigError(pfad, "'format' und 'decimals' schliessen sich aus")
    return spec


def _icon_spec(wert: Any, pfad: str) -> IconSpec:
    if isinstance(wert, str):
        return IconSpec(name=wert)
    d = _dict(wert, pfad)
    _unbekannt(d, schema.ICON_KEYS, pfad)
    spec = IconSpec(
        name=d.get("name"),
        entity=d.get("value"),
        map={str(k): str(v) for k, v in _dict(d.get("map", {}), f"{pfad}.map").items()},
        default=d.get("default"),
        template=d.get("template"),
    )
    if "steps" in d:
        stufen = _dict(d["steps"], f"{pfad}.steps")
        try:
            spec.steps = sorted(((float(k), str(v)) for k, v in stufen.items()), reverse=True)
        except (TypeError, ValueError):
            raise ConfigError(f"{pfad}.steps",
                              "Schluessel muessen Zahlen sein (Schwelle -> Symbolname)") from None
        if not spec.entity:
            raise ConfigError(pfad, "'steps' braucht 'value' (die Entitaet, die entscheidet)")
    if spec.map and not spec.entity:
        raise ConfigError(pfad, "'map' braucht 'value' (die Entitaet, die entscheidet)")
    if not (spec.name or spec.entity or spec.template):
        raise ConfigError(pfad, "Symbol braucht 'name', 'value' oder 'template'")
    return spec


WIDGET_SCHLUESSEL = schema.WIDGET_KEYS

EINGEBAUTE_TYPEN = set(schema.WIDGET_TYPEN)


def typen() -> set[str]:
    """Alle gerade gueltigen Widget-Typen — eingebaute plus geladene eigene.

    ⚠ Eine Funktion und keine Konstante: die eigenen Typen stehen erst fest, wenn
    `plugin.registry.lade()` gelaufen ist, und sie aendern sich bei „Neu laden". Eine
    Momentaufnahme beim Import waere immer leer.
    """
    return EINGEBAUTE_TYPEN | set(plugin.registry.namen())


def _plugin_wert(roh: Any, f: schema.Feld, pfad: str) -> Any:
    """Einen Wert fuer ein vom Plugin angemeldetes Feld pruefen und umrechnen."""
    if f.art == "int":
        wert: Any = _int(roh, pfad)
    elif f.art == "float":
        try:
            wert = float(roh)
        except (TypeError, ValueError):
            raise ConfigError(pfad, f"keine Zahl: {roh!r}") from None
    elif f.art == "bool":
        if not isinstance(roh, bool):
            raise ConfigError(pfad, f"true oder false erwartet, nicht {roh!r}")
        wert = roh
    elif f.art == "farbe":
        wert = _farbe(roh, pfad)
    elif f.art == "auswahl":
        wert = str(roh)
        if wert not in f.optionen:
            raise ConfigError(pfad, f"unbekannt: {wert!r} — erlaubt: {', '.join(f.optionen)}")
    else:
        # text, entitaet, schrift, symbol, vorlage, format — alles Zeichenketten
        wert = str(roh)

    if f.art in ("int", "float"):
        if f.min is not None and wert < f.min:
            raise ConfigError(pfad, f"{wert} ist kleiner als {f.min}")
        if f.max is not None and wert > f.max:
            raise ConfigError(pfad, f"{wert} ist groesser als {f.max}")
    return wert


def _plugin_werte(d: dict, eigen, pfad: str) -> dict[str, Any]:
    werte: dict[str, Any] = {}
    for f in eigen.felder:
        if f.name not in d:
            if f.pflicht:
                raise ConfigError(f"{pfad}.{f.name}",
                                  f"fehlt — type: {eigen.name} braucht es ({eigen.quelle})")
            if f.vorgabe is not None:
                werte[f.name] = f.vorgabe
            continue
        werte[f.name] = _plugin_wert(d[f.name], f, f"{pfad}.{f.name}")
    return werte


def _widget(wert: Any, pfad: str, grid: Grid, vorgabe_font: str, vorgabe_farbe: str) -> Widget:
    d = _dict(wert, pfad)

    # ★ Der Typ wird VOR den Schluesseln geprueft, nicht danach: welche Schluessel erlaubt
    # sind, haengt bei eigenen Typen am Typ selbst. Nebenwirkung, die so gewollt ist — wer
    # sich beim Typ vertippt, liest jetzt „unbekannter Typ" statt einer Liste unbekannter
    # Schluessel, die nur die Folge davon ist.
    typ = str(d.get("type", "tile"))
    # ⚠ Vor allem anderen: ein veralteter Typname wird auf den aktuellen umgeschrieben.
    # Sonst scheitert die Pruefung unten mit „unbekannter Typ" an etwas, das gestern noch
    # richtig war — dieselbe Ueberlegung wie bei den Schluesselnamen (`_umbenannt`).
    if typ in schema.TYP_UMBENANNT:
        _LOG.info("%s: type %r heisst jetzt %r — bitte bei Gelegenheit umschreiben",
                  pfad, typ, schema.TYP_UMBENANNT[typ])
        typ = schema.TYP_UMBENANNT[typ]
    eigen = plugin.registry.get(typ)
    if eigen is None and typ not in EINGEBAUTE_TYPEN:
        alle = typen()
        hinweis = ""
        if not plugin.registry.aktiv:
            hinweis = (" — eigene Typen aus /config/aton_widgets sind aus, siehe "
                       "App-Option 'custom_widgets'")
        raise ConfigError(f"{pfad}.type",
                          f"unbekannt: {typ!r} — erlaubt: {', '.join(sorted(alle))}{hinweis}")

    erlaubt = WIDGET_SCHLUESSEL | (eigen.schluessel if eigen else set())
    ueber = set(d) - erlaubt
    if ueber:
        # ★ Der haeufigste Fall ist kein Tippfehler, sondern ein TYPWECHSEL: `sensor:` von
        # einem `bargraph` blieb stehen, und `clock` kennt ihn nicht. Ohne diesen Zusatz
        # liest man „unbekannter Schluessel" und sucht einen Vertipper, den es nicht gibt —
        # den Schluessel hat nie jemand hingeschrieben.
        herkunft = {n: t for n in sorted(ueber)
                    if (t := plugin.registry.typ_von_schluessel(n)) and t != typ}
        zusatz = ""
        if herkunft:
            teile = ", ".join(f"{n} gehoert zu type: {t}" for n, t in herkunft.items())
            zusatz = (f" — {teile}. Beim Wechsel des Typs bleiben die Schluessel des alten "
                      "stehen; hier sind sie zu loeschen")
        raise ConfigError(pfad, "unbekannte Schluessel: " + ", ".join(sorted(ueber))
                          + zusatz + " — erlaubt sind: " + ", ".join(sorted(erlaubt)))

    # Lage: entweder absolut (at) oder ueber das Raster (cell)
    if "at" in d and "cell" in d:
        raise ConfigError(pfad, "'at' und 'cell' schliessen sich aus")
    if "cell" in d:
        zelle = _liste(d["cell"], f"{pfad}.cell")
        if len(zelle) != 2:
            raise ConfigError(f"{pfad}.cell", "muss [zeile, spalte] sein")
        zeile, spalte = _int(zelle[0], f"{pfad}.cell[0]"), _int(zelle[1], f"{pfad}.cell[1]")
        x, y = spalte * grid.col_width, zeile * grid.row_height
        ueber_zelle = True
    elif "at" in d:
        stelle = _liste(d["at"], f"{pfad}.at")
        if len(stelle) != 2:
            raise ConfigError(f"{pfad}.at", "muss [x, y] sein")
        x, y = _int(stelle[0], f"{pfad}.at[0]"), _int(stelle[1], f"{pfad}.at[1]")
    else:
        raise ConfigError(pfad, "Lage fehlt: 'cell: [zeile, spalte]' oder 'at: [x, y]'")
    ueber_zelle = "cell" in d

    w, h = grid.col_width, 8
    if "size" in d:
        groesse = _liste(d["size"], f"{pfad}.size")
        if len(groesse) != 2:
            raise ConfigError(f"{pfad}.size", "muss [breite, hoehe] sein")
        w, h = _int(groesse[0], f"{pfad}.size[0]"), _int(groesse[1], f"{pfad}.size[1]")

    # Die Farbe darf wie das Symbol aus dem Zustand kommen (z.B. rot bei Handlungsbedarf).
    roh_farbe = d.get("color", vorgabe_farbe)
    farbe_wert: str | IconSpec = (_icon_spec(roh_farbe, f"{pfad}.color")
                                  if isinstance(roh_farbe, dict)
                                  else _farbe(roh_farbe, f"{pfad}.color"))

    widget = Widget(
        type=typ, x=x, y=y, w=w, h=h,
        color=farbe_wert,
        bg=_farbe(d["bg"], f"{pfad}.bg") if "bg" in d else None,
        font=str(d.get("font", vorgabe_font)),
        align=str(d.get("align", "left")),
        image=d.get("image"),
        layer=_int(d.get("layer", 0), f"{pfad}.layer"),
        visible_when=d.get("visible_when"),
        pfad=pfad,
        cell_benutzt=ueber_zelle,
    )
    if widget.align not in ("left", "center", "right"):
        raise ConfigError(f"{pfad}.align", "erlaubt: left, center, right")

    if "icon" in d:
        widget.icon = _icon_spec(d["icon"], f"{pfad}.icon")
    widget.text = _text_spec(d, pfad)

    if "text_at" in d:
        stelle = _liste(d["text_at"], f"{pfad}.text_at")
        if len(stelle) != 2:
            raise ConfigError(f"{pfad}.text_at", "muss [x, y] sein")
        widget.text_x = _int(stelle[0], f"{pfad}.text_at[0]")
        widget.text_y = _int(stelle[1], f"{pfad}.text_at[1]")
    if "text_width" in d:
        widget.text_w = _int(d["text_width"], f"{pfad}.text_width")

    # Plausibilitaet je Typ
    if typ == "tile" and not widget.icon and not widget.text:
        raise ConfigError(pfad, "eine Kachel braucht 'icon' und/oder einen Text")
    if typ == "icon" and not widget.icon:
        raise ConfigError(pfad, "type: icon braucht 'icon'")
    if typ == "text" and not widget.text:
        raise ConfigError(pfad, "type: text braucht 'text', 'value' oder 'template'")
    if typ == "image" and not widget.image:
        raise ConfigError(pfad, "type: image braucht 'image' (Dateiname in aton_icons)")

    if typ in ("bar", "sparkline"):
        # ★ `min`/`max` bleiben BEWUSST None, wenn sie fehlen. Bei `bar` setzt der
        # Renderer 0..100 ein, bei `sparkline` heisst None „nimm die Spanne der Daten" —
        # eine feste 0 waere dort das Gegenteil von hilfreich: eine Aussentemperatur um
        # 20 °C ergaebe eine Linie ganz oben ohne jede sichtbare Bewegung.
        if "scale_min" in d:
            widget.skala_min = _float(d["scale_min"], f"{pfad}.scale_min")
        if "scale_max" in d:
            widget.skala_max = _float(d["scale_max"], f"{pfad}.scale_max")
        if not widget.text:
            raise ConfigError(pfad, f"type: {typ} braucht eine Textquelle, die den Wert "
                                    "liefert — 'value' (Entitaet) oder 'template'")

    if typ == "bar":
        if d.get("track"):
            widget.track = _farbe(d["track"], f"{pfad}.track")
        widget.vertical = bool(d.get("vertical", False))

    if typ == "sparkline":
        widget.hours = _int(d.get("hours", 24), f"{pfad}.hours")
        if not 1 <= widget.hours <= 168:
            raise ConfigError(f"{pfad}.hours", "muss zwischen 1 und 168 liegen")
        if d.get("fill"):
            widget.fill = _farbe(d["fill"], f"{pfad}.fill")
        # ⚠ Der Verlauf kommt NICHT aus einer Vorlage, sondern aus dem Recorder — dafuer
        # braucht es die Entitaet selbst, nicht ihren gerenderten Text. Ein `template:`
        # koennte alles Moegliche liefern; welche Entitaet abzufragen waere, stuende
        # nirgends.
        if not widget.text.entity:
            raise ConfigError(pfad, "type: sparkline braucht 'value' (die Entitaet, deren "
                                    "Verlauf gezeichnet wird) — 'template' reicht nicht, "
                                    "der Verlauf wird beim Recorder erfragt")

    if typ == "lines":
        widget.max_rows = _int(d.get("max_rows", 0), f"{pfad}.max_rows")
        if "separator" in d:
            widget.separator = str(d["separator"])
        if "line_spacing" in d:
            widget.line_spacing = _int(d["line_spacing"], f"{pfad}.line_spacing")
        if not widget.text:
            raise ConfigError(pfad, "type: lines braucht eine Textquelle, die die Zeilen "
                                    "liefert — 'template', 'value' oder 'text'")

    if typ in ("icons", "series"):
        widget.spacing = _int(d.get("spacing", 1), f"{pfad}.spacing")
        if "line_spacing" in d:
            widget.line_spacing = _int(d["line_spacing"], f"{pfad}.line_spacing")
        if "cell_size" in d:
            groesse = _liste(d["cell_size"], f"{pfad}.cell_size")
            if len(groesse) != 2:
                raise ConfigError(f"{pfad}.cell_size", "muss [breite, hoehe] sein")
            widget.cell_w = _int(groesse[0], f"{pfad}.cell_size[0]")
            widget.cell_h = _int(groesse[1], f"{pfad}.cell_size[1]")
        if not widget.text:
            quelle = ("die Symbolnamen" if typ == "icons"
                      else "die Spalten (Reihen durch `|`, `@name` ist ein Symbol)")
            raise ConfigError(pfad, f"type: {typ} braucht eine Textquelle, die {quelle} "
                                    "liefert — 'template', 'value' oder 'text'")

    if typ == "series":
        # ⚠ Farben HIER pruefen, nicht erst beim Zeichnen: eine krumme Farbe wuerde sonst
        # jeden Frame eine Ausnahme werfen und die Kachel kosten, ohne zu sagen, wo sie
        # steht. Der Pfad in der Meldung nennt die Stelle in der YAML.
        widget.row_colors = [(_farbe(t, f"{pfad}.row_colors[{i}]") if t else "")
                             for i, t in enumerate(_liste_oder_kommaliste(
                                 d.get("row_colors"), f"{pfad}.row_colors"))]
        widget.row_fonts = _liste_oder_kommaliste(d.get("row_fonts"), f"{pfad}.row_fonts")

    if typ == "notify":
        # Der Text kommt aus der MELDUNG, nicht aus der Beschreibung. `text:`/`value:`
        # duerfen trotzdem dastehen und werden ignoriert — wie `icon:` an einer Uhr. Sie
        # abzulehnen machte jeden Typwechsel zur Sackgasse (siehe 0.12.5/0.12.6).
        widget.notify = _meldung(d, pfad, vorgabe_font)

    if eigen:
        widget.optionen = _plugin_werte(d, eigen, pfad)
        widget.optionen_entitaeten = set(eigen.entitaets_felder)
    return widget


def _widgets(wert: Any, pfad: str, grid: Grid, font: str, farbe: str) -> list[Widget]:
    return [_widget(w, f"{pfad}[{i}]", grid, font, farbe)
            for i, w in enumerate(_liste(wert, pfad))]


def _screen_group(wert: Any, pfad: str, grid: Grid, font: str, farbe: str,
                  interval: float = 5.0) -> ScreenGroup:
    d = _dict(wert, pfad)
    # `interval` nur fuer die Uebernahme veralteter Sekundenangaben (siehe _umbenannt).
    _entfernt(d, "screen_group", pfad)
    _unbekannt(d, schema.SCREEN_GROUP_KEYS, pfad)
    gid = str(_pflicht(d, "id", pfad))
    gruppe = ScreenGroup(
        id=gid,
        name=str(d.get("name", gid)),
        region=_rechteck(_pflicht(d, "region", pfad), f"{pfad}.region"),
    )
    for i, s in enumerate(_liste(_pflicht(d, "screens", pfad), f"{pfad}.screens")):
        sp = f"{pfad}.screens[{i}]"
        sd = _dict(s, sp)
        sd = _umbenannt(sd, "screen", sp, interval=interval)
        _unbekannt(sd, schema.SCREEN_KEYS, sp)
        when = sd.get("when")
        if isinstance(when, str) and when.strip().lower() in ("always", "immer"):
            when = None

        if "pages" in sd:
            if "widgets" in sd:
                raise ConfigError(sp, "entweder `widgets:` oder `pages:` — nicht beides. "
                                      "Die Kacheln gehoeren dann in die erste Seite")
            seiten = []
            for j, roh in enumerate(_liste(sd["pages"], f"{sp}.pages")):
                pp = f"{sp}.pages[{j}]"
                pd = _umbenannt(_dict(roh, pp), "seite", pp)
                _unbekannt(pd, schema.SEITE_KEYS, pp)
                seiten.append(Seite(
                    name=str(pd.get("name", f"Seite {j + 1}")),
                    widgets=_widgets(pd.get("widgets", []), f"{pp}.widgets",
                                     grid, font, farbe),
                    zyklen=max(0, _int(pd.get("cycles", 0), f"{pp}.cycles"))))
            if not seiten:
                raise ConfigError(f"{sp}.pages", "mindestens eine Seite noetig")
        else:
            # Der Normalfall bleibt unveraendert: eine Seite, die niemand so nennen muss.
            seiten = [Seite(name=str(_pflicht(sd, "name", sp)),
                            widgets=_widgets(sd.get("widgets", []), f"{sp}.widgets",
                                             grid, font, farbe))]

        gruppe.screens.append(Screen(
            name=str(_pflicht(sd, "name", sp)),
            when=when,
            seiten=seiten,
            wechsel_zyklen=max(0, _int(sd.get("page_cycles", 0),
                                       f"{sp}.page_cycles")),
        ))
    if not gruppe.screens:
        raise ConfigError(f"{pfad}.screens", "mindestens ein Screen noetig")
    namen = [s.name for s in gruppe.screens]
    if len(set(namen)) != len(namen):
        raise ConfigError(f"{pfad}.screens", "Screen-Namen muessen eindeutig sein")
    return gruppe


def _meldung(d: dict, pfad: str, vorgabe_font: str) -> NotifyCfg:
    """Die Einstellungen einer Meldezeile — aus dem Block `notify:` ODER einem Widget.

    ★ Bewusst EINE Funktion fuer beide Schreibweisen: liefe die Auswertung zweimal, waere
    schon die naechste Vorgabe (`max_bar_chars: 30`) eine Stelle, an der sich Block und
    Widget unbemerkt unterscheiden koennen. Die Lage kommt von aussen — der Block hat
    `region`, das Widget `at`/`size`.
    """
    cfg = NotifyCfg(
        visible_when=d.get("visible_when"),
        max_bar_chars=_int(d.get("max_bar_chars", 30), f"{pfad}.max_bar_chars"),
        max_chars=_int(d.get("max_chars", 60), f"{pfad}.max_chars"),
        font=str(d.get("font", vorgabe_font)),
        scroll_speed=_int(d.get("scroll_speed", 128), f"{pfad}.scroll_speed"),
        scroll_yoff=_int(d.get("scroll_yoff", 128), f"{pfad}.scroll_yoff"),
        scroll_font=_int(d.get("scroll_font", 128), f"{pfad}.scroll_font"),
        channel=(str(d["channel"]).strip() or None) if d.get("channel") else None,
        show_levels=_stufen(d.get("show_levels"), f"{pfad}.show_levels"),
    )
    if "levels" in d:
        stufen = {}
        for name, v in _dict(d["levels"], f"{pfad}.levels").items():
            lp = f"{pfad}.levels.{name}"
            ld = _dict(v, lp)
            _unbekannt(ld, schema.LEVEL_KEYS, lp)
            stufen[str(name)] = (_farbe(ld.get("bg", "000000"), f"{lp}.bg"),
                                 _farbe(ld.get("fg", "ffffff"), f"{lp}.fg"))
        if stufen:
            cfg.levels = stufen
    if cfg.show_levels - set(cfg.levels):
        # Ein Filter auf eine Stufe, die diese Zeile gar nicht kennt, laesst sie fuer immer
        # leer — und das sieht aus wie „die Meldung kam nicht an".
        raise ConfigError(f"{pfad}.show_levels",
                          "unbekannte Stufe(n): "
                          + ", ".join(sorted(cfg.show_levels - set(cfg.levels)))
                          + " — bekannt sind: " + ", ".join(sorted(cfg.levels)))
    return cfg


def _liste_oder_kommaliste(wert: Any, pfad: str) -> list[str]:
    """Eine Liste — geschrieben als YAML-Liste ODER als Kommaliste.

    Beides zuzulassen ist kein Luxus: in der YAML liest sich `[ffff00, '', 30c030]`
    natuerlich, im Formular des Konfigurators gibt es fuer solche Listen kein Feld, dort
    tippt man `ffff00, , 30c030`. Reihenfolge und leere Eintraege bleiben in beiden Faellen
    erhalten — die Stelle in der Liste IST die Zuordnung zur Reihe.
    """
    if wert is None or wert == "":
        return []
    if isinstance(wert, str):
        return [t.strip() for t in wert.split(",")]
    if isinstance(wert, list):
        return [str(t).strip() if t is not None else "" for t in wert]
    raise ConfigError(pfad, "muss eine Liste oder eine Kommaliste sein, "
                            f"ist {type(wert).__name__}")


def _stufen(wert: Any, pfad: str) -> set[str]:
    """`show_levels` als Liste oder als Kommaliste — die Oberflaeche schreibt Text."""
    if wert is None or wert == "":
        return set()
    if isinstance(wert, str):
        return {t.strip() for t in wert.split(",") if t.strip()}
    if isinstance(wert, list):
        return {str(t).strip() for t in wert if str(t).strip()}
    raise ConfigError(pfad, "muss eine Liste oder eine Kommaliste sein, "
                            f"ist {type(wert).__name__}")


def _notify(wert: Any, pfad: str, vorgabe_font: str) -> NotifyCfg:
    d = _dict(wert, pfad)
    _unbekannt(d, schema.NOTIFY_KEYS, pfad)
    cfg = _meldung(d, pfad, vorgabe_font)
    cfg.region = _rechteck(_pflicht(d, "region", pfad), f"{pfad}.region")
    return cfg


PANEL_SCHLUESSEL = schema.PANEL_KEYS


def _panel(wert: Any, pfad: str, vorgaben: dict) -> PanelCfg:
    d = _dict(wert, pfad)
    _unbekannt(d, PANEL_SCHLUESSEL, pfad)

    groesse = _liste(_pflicht(d, "size", pfad), f"{pfad}.size")
    if len(groesse) != 2:
        raise ConfigError(f"{pfad}.size", "muss [breite, hoehe] sein")

    grid = Grid()
    if "grid" in d:
        gd = _dict(d["grid"], f"{pfad}.grid")
        _unbekannt(gd, schema.GRID_KEYS, f"{pfad}.grid")
        grid = Grid(
            row_height=_int(gd.get("row_height", 9), f"{pfad}.grid.row_height"),
            col_width=_int(gd.get("col_width", 32), f"{pfad}.grid.col_width"),
            icon_width=_int(gd.get("icon_width", 8), f"{pfad}.grid.icon_width"),
            gap=_int(gd.get("gap", 1), f"{pfad}.grid.gap"),
        )

    font = str(vorgaben.get("font", DEFAULT_FONT))
    farbe = _farbe(vorgaben.get("color", DEFAULT_COLOR), "defaults.color")

    pid = str(_pflicht(d, "id", pfad))
    panel = PanelCfg(
        id=pid,
        name=str(d.get("name", pid)),
        host=str(_pflicht(d, "host", pfad)),
        width=_int(groesse[0], f"{pfad}.size[0]"),
        height=_int(groesse[1], f"{pfad}.size[1]"),
        interval=_float(d.get("interval", vorgaben.get("interval", DEFAULT_INTERVAL)),
                        f"{pfad}.interval"),
        full_frame_every=_int(d.get("full_frame_every", 60), f"{pfad}.full_frame_every"),
        canvas_segment=_int(d.get("canvas_segment", 0), f"{pfad}.canvas_segment"),
        scroll_segment=_int(d.get("scroll_segment", 1), f"{pfad}.scroll_segment"),
        clear_segments_to=_int(d.get("clear_segments_to", 32), f"{pfad}.clear_segments_to"),
        dry_run=bool(d.get("dry_run", False)),
        led_pitch=(_float(d["led_pitch"], f"{pfad}.led_pitch") if d.get("led_pitch") else None),
        grid=grid,
    )
    if not pid.replace("_", "").replace("-", "").isalnum():
        raise ConfigError(f"{pfad}.id", "nur Buchstaben, Ziffern, '-' und '_' (wird zur Entity-ID)")

    if "gate" in d:
        gd = _dict(d["gate"], f"{pfad}.gate")
        _unbekannt(gd, schema.GATE_KEYS, f"{pfad}.gate")
        panel.gate_entity = gd.get("entity")
        panel.gate_fallback = gd.get("fallback")
        panel.gate_script = gd.get("script")
        if "wartezeit" in gd:
            panel.gate_wartezeit = _int(gd["wartezeit"], f"{pfad}.gate.wartezeit")
    if "brightness" in d:
        bd = _dict(d["brightness"], f"{pfad}.brightness")
        _unbekannt(bd, schema.BRIGHTNESS_KEYS, f"{pfad}.brightness")
        panel.brightness_entity = bd.get("entity")
        panel.brightness_default = _int(bd.get("default", 128), f"{pfad}.brightness.default")

    panel.widgets = _widgets(d.get("widgets", []), f"{pfad}.widgets", grid, font, farbe)
    panel.groups = [_screen_group(g, f"{pfad}.screen_groups[{i}]", grid, font, farbe,
                                  panel.interval)
                    for i, g in enumerate(_liste(d.get("screen_groups", []),
                                                 f"{pfad}.screen_groups"))]
    gids = [g.id for g in panel.groups]
    if len(set(gids)) != len(gids):
        raise ConfigError(f"{pfad}.screen_groups", "Gruppen-IDs muessen eindeutig sein")

    if "notify" in d:
        # ★ Der Block ist seit 0.13.0 nur noch eine Schreibweise fuer eine Kachel
        # `type: notify`. Uebersetzt wird HIER, damit es weiter unten nur noch einen Fall
        # gibt: Renderer, Transport und die Stufenpruefung kennen ausschliesslich
        # Meldezeilen-Widgets. `panel.notify` bleibt daneben stehen — der Konfigurator
        # zeichnet daraus den Bereich in der Vorschau und bietet den Block zum Bearbeiten
        # an, solange er in der Datei steht.
        panel.notify = _notify(d["notify"], f"{pfad}.notify", font)
        x, y, w, h = panel.notify.region
        panel.overlays.append(Widget(
            type="notify", x=x, y=y, w=w, h=h,
            font=panel.notify.font,
            visible_when=panel.notify.visible_when,
            # Ueber allem: der Block lag im Renderer schon immer nach den Screen-Gruppen,
            # und genau das muss die Uebersetzung erhalten.
            layer=1,
            notify=panel.notify,
            pfad=f"{pfad}.notify",
        ))

    # Liegt alles im Bild?
    for g in panel.groups:
        x, y, w, h = g.region
        if x < 0 or y < 0 or x + w > panel.width or y + h > panel.height:
            raise ConfigError(f"{pfad}.screen_groups[{gids.index(g.id)}].region",
                              f"liegt ausserhalb der Flaeche {panel.width}x{panel.height}")
    if panel.notify.region:
        x, y, w, h = panel.notify.region
        if x < 0 or y < 0 or x + w > panel.width or y + h > panel.height:
            raise ConfigError(f"{pfad}.notify.region",
                              f"liegt ausserhalb der Flaeche {panel.width}x{panel.height}")
    _scroll_segmente(panel, pfad)
    return panel


def _scroll_segmente(panel: PanelCfg, pfad: str) -> None:
    """Jeder Meldezeile ein eigenes WLED-Segment geben — fest, nicht je Meldung.

    ★★ Warum das hier steht und nicht im Renderer: die Zuteilung muss **stabil** sein.
    Wenn Zeile A aufhoert zu laufen und B anfaengt, darf B nicht A's Segment bekommen —
    WLED wuerde sonst die Animation von A neu starten (der Scroll-Offset `SEGENV.aux0`
    haengt am Segment). Im Renderer waere die Reihenfolge vom gerade aktiven Screen
    abhaengig und damit gerade nicht stabil.

    ★ Mehrere Laufschriften gehen ueberhaupt erst seit 0.21.1. Vorher gab es genau ein
    Segment, und die zweite Meldung bekam eine Absage. Am WLED-Quelltext geprueft ist das
    kein Geraete-Limit: `SEGENV` IST das Segment (`FX.h`), Offset, Farbschritt und Taktung
    liegen also je Segment getrennt; `service()` bedient sie in Index-Reihenfolge.
    """
    zeilen = [w for w in panel.alle_widgets() if w.type == "notify"]
    for i, w in enumerate(zeilen):
        w.scroll_segment = panel.scroll_segment + i

    # ⚠ Die Bildflaeche darf nicht ueberschrieben werden, und `clear_segments_to` raeumt
    # alles OBERHALB der Laufschriften weg — beides muss zu der Zahl passen. Lieber beim
    # Laden mit Pfad scheitern als im Betrieb ein Segment ueberbuegeln.
    hoechstes = panel.scroll_segment + max(0, len(zeilen) - 1)
    if panel.scroll_segment <= panel.canvas_segment:
        raise ConfigError(f"{pfad}.scroll_segment",
                          f"muss ueber der Bildflaeche liegen (canvas_segment "
                          f"{panel.canvas_segment})")
    if hoechstes >= panel.clear_segments_to:
        raise ConfigError(
            f"{pfad}.scroll_segment",
            f"{len(zeilen)} Meldezeile(n) brauchen die Segmente {panel.scroll_segment}"
            f"..{hoechstes}, aber `clear_segments_to` raeumt ab {panel.clear_segments_to} "
            "auf. Entweder clear_segments_to erhoehen (WLEDs MAX_NUM_SEGMENTS ist auf "
            "ESP32 32) oder weniger Meldezeilen")


class _Loader(yaml.SafeLoader):
    """SafeLoader ohne die YAML-1.1-Wahrheitswerte `on`/`off`/`yes`/`no`.

    ★ Gemessener Fehler, nicht vermutet: `map: {off: dry, on: wet}` wurde von PyYAML zu
    `{False: 'dry', True: 'wet'}`. Der Zustand einer HA-Entitaet ist aber die
    ZEICHENKETTE "off" — der Vergleich schlug also immer fehl, und still griff der
    `default`. Auf der Matrix hiess das: bei trockenem Wetter stand dauerhaft das
    Regensymbol. Aufgefallen ist es nur, weil der Konfigurator (ruamel, YAML 1.2) ein
    anderes Symbol zeichnete als die laufende Anzeige.

    `true`/`false` bleiben Wahrheitswerte — die braucht `enabled: true` und dergleichen.
    """


_Loader.add_implicit_resolver(
    "tag:yaml.org,2002:bool",
    re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
    list("tTfF"))
# Die uebrigen Anfangsbuchstaben der 1.1-Liste (y/Y/n/N/o/O) verlieren damit ihren
# bool-Aufloeser und fallen auf `str` zurueck.
for _b in list("yYnNoO"):
    _Loader.yaml_implicit_resolvers[_b] = [
        (t, r) for (t, r) in _Loader.yaml_implicit_resolvers.get(_b, [])
        if t != "tag:yaml.org,2002:bool"]


def lade(pfad: str) -> AppCfg:
    if not os.path.exists(pfad):
        raise ConfigError(pfad, "Datei nicht gefunden — Beispiel siehe DOCS.md")
    with open(pfad, "r", encoding="utf-8") as fh:
        try:
            roh = yaml.load(fh, Loader=_Loader)
        except yaml.YAMLError as e:
            raise ConfigError(pfad, f"kein gueltiges YAML: {e}") from None
    return pruefe(roh, pfad)


def pruefe(roh, quelle: str = "(Daten)") -> AppCfg:
    """Bereits eingelesene Daten pruefen.

    Getrennt von `lade`, damit der Konfigurator einen Entwurf pruefen und rendern kann,
    OHNE ihn vorher zu speichern — man soll sehen, was herauskommt, bevor man es
    festschreibt.
    """
    pfad = quelle
    if roh is None:
        raise ConfigError(pfad, "Datei ist leer")
    d = _dict(roh, "(Wurzel)")
    _unbekannt(d, schema.WURZEL_KEYS, "(Wurzel)")

    vorgaben = _dict(d.get("defaults", {}), "defaults")
    _unbekannt(vorgaben, schema.DEFAULTS_KEYS, "defaults")

    # Schrift-Eigenschaften: Grossschrift und Umlaut-Ersatzschreibung gehoeren zur
    # SCHRIFT (in 5 px ist beides noetig, in 8x16 nicht) und nicht in den Code.
    schriften: dict[str, dict] = {}
    for name, wert in _dict(d.get("fonts", {}), "fonts").items():
        pfad_f = f"fonts.{name}"
        fd = _dict(wert, pfad_f)
        _unbekannt(fd, schema.SCHRIFT_KEYS, pfad_f)
        schriften[str(name)] = {k: bool(v) for k, v in fd.items()}

    panels = [_panel(p, f"panels[{i}]", vorgaben)
              for i, p in enumerate(_liste(_pflicht(d, "panels", "(Wurzel)"), "panels"))]
    if not panels:
        raise ConfigError("panels", "mindestens eine Anzeige noetig")
    ids = [p.id for p in panels]
    if len(set(ids)) != len(ids):
        raise ConfigError("panels", "Anzeigen-IDs muessen eindeutig sein")
    return AppCfg(panels=panels, fonts=schriften, quelle=quelle)
