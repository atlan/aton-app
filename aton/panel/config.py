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

from . import schema
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
    # Rastermass der Matrix in Millimetern (P3 = 3.0). Rein fuer die DARSTELLUNG:
    # bezieht den Zoom der Vorschau darauf und zeichnet die LEDs als Punkte. Auf das,
    # was an WLED geht, hat es keinen Einfluss.
    led_pitch: float | None = None
    gate_entity: str | None = None
    gate_fallback: str | None = None
    gate_script: str | None = None
    brightness_entity: str | None = None
    brightness_default: int = 128
    grid: Grid = field(default_factory=Grid)
    widgets: list[Widget] = field(default_factory=list)
    groups: list[ScreenGroup] = field(default_factory=list)
    notify: NotifyCfg = field(default_factory=NotifyCfg)

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
        _LOG.warning("%s: %r heisst jetzt %r (Wert uebernommen: %r) — beim naechsten "
                     "Speichern im Konfigurator wird es umgeschrieben",
                     pfad, alt, neu_name, d[neu_name])
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

TYPEN = set(schema.WIDGET_TYPEN)


def _widget(wert: Any, pfad: str, grid: Grid, vorgabe_font: str, vorgabe_farbe: str) -> Widget:
    d = _dict(wert, pfad)
    _unbekannt(d, WIDGET_SCHLUESSEL, pfad)

    typ = str(d.get("type", "tile"))
    if typ not in TYPEN:
        raise ConfigError(f"{pfad}.type", f"unbekannt: {typ!r} — erlaubt: {', '.join(sorted(TYPEN))}")

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

        if "seiten" in sd:
            if "widgets" in sd:
                raise ConfigError(sp, "entweder `widgets:` oder `seiten:` — nicht beides. "
                                      "Die Kacheln gehoeren dann in die erste Seite")
            seiten = []
            for j, roh in enumerate(_liste(sd["seiten"], f"{sp}.seiten")):
                pp = f"{sp}.seiten[{j}]"
                pd = _dict(roh, pp)
                _unbekannt(pd, schema.SEITE_KEYS, pp)
                seiten.append(Seite(
                    name=str(pd.get("name", f"Seite {j + 1}")),
                    widgets=_widgets(pd.get("widgets", []), f"{pp}.widgets",
                                     grid, font, farbe),
                    zyklen=max(0, _int(pd.get("zyklen", 0), f"{pp}.zyklen"))))
            if not seiten:
                raise ConfigError(f"{sp}.seiten", "mindestens eine Seite noetig")
        else:
            # Der Normalfall bleibt unveraendert: eine Seite, die niemand so nennen muss.
            seiten = [Seite(name=str(_pflicht(sd, "name", sp)),
                            widgets=_widgets(sd.get("widgets", []), f"{sp}.widgets",
                                             grid, font, farbe))]

        gruppe.screens.append(Screen(
            name=str(_pflicht(sd, "name", sp)),
            when=when,
            seiten=seiten,
            wechsel_zyklen=max(0, _int(sd.get("wechsel_zyklen", 0),
                                       f"{sp}.wechsel_zyklen")),
        ))
    if not gruppe.screens:
        raise ConfigError(f"{pfad}.screens", "mindestens ein Screen noetig")
    namen = [s.name for s in gruppe.screens]
    if len(set(namen)) != len(namen):
        raise ConfigError(f"{pfad}.screens", "Screen-Namen muessen eindeutig sein")
    return gruppe


def _notify(wert: Any, pfad: str, vorgabe_font: str) -> NotifyCfg:
    d = _dict(wert, pfad)
    _unbekannt(d, schema.NOTIFY_KEYS, pfad)
    cfg = NotifyCfg(
        region=_rechteck(_pflicht(d, "region", pfad), f"{pfad}.region"),
        visible_when=d.get("visible_when"),
        max_bar_chars=_int(d.get("max_bar_chars", 30), f"{pfad}.max_bar_chars"),
        max_chars=_int(d.get("max_chars", 60), f"{pfad}.max_chars"),
        font=str(d.get("font", vorgabe_font)),
        scroll_speed=_int(d.get("scroll_speed", 128), f"{pfad}.scroll_speed"),
        scroll_yoff=_int(d.get("scroll_yoff", 128), f"{pfad}.scroll_yoff"),
        scroll_font=_int(d.get("scroll_font", 128), f"{pfad}.scroll_font"),
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
        panel.notify = _notify(d["notify"], f"{pfad}.notify", font)

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
    return panel


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
