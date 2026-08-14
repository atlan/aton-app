"""Veraltete Namen in der Beschreibung auf die aktuellen umschreiben.

★ Der Lader (`config.py`) nimmt veraltete Namen NUR entgegen — er arbeitet auf einer Kopie
und laesst die Datei in Ruhe. Das ist dort richtig so: wer von Hand schreibt, will nicht,
dass ihm jemand die Datei umbaut. Der Konfigurator schreibt die Datei aber ohnehin neu,
und dann ist es unehrlich, den alten Namen stehenzulassen: das Formular zeigt die Felder
des NEUEN Typs, die Datei sagt den ALTEN. Genau daran ist einmal auffaellig geworden, dass
eine Kachel mit `type: serie` im Konfigurator keine `row_*`-Felder bekam.

Deshalb hier: dieselben Tabellen (`schema.UMBENANNT`, `schema.TYP_UMBENANNT`), aber an Ort
und Stelle angewandt — auf den Entwurf aus dem Browser UND auf die vorhandene Struktur aus
der Datei. Beide muessen migriert sein, sonst sieht die Verschmelzung in `configfile` einen
geloeschten und einen neuen Schluessel und haengt ihn samt Kommentarverlust ans Ende.

⚠ Umbenannt wird POSITIONSTREU (`CommentedMap.insert`) und mit dem Kommentar des
Schluessels im Gepaeck. Ein Umbenennen ueber `d[neu] = d.pop(alt)` wuerde den Eintrag ans
Ende der Zuordnung schieben — die Datei bliebe gueltig, saehe aber jedes Mal anders aus.

⚠ Nichts hier darf ein Speichern verhindern. Was sich nicht uebernehmen laesst, bleibt
stehen und wird protokolliert; die Beschwerde kommt dann wie bisher vom Lader.
"""
from __future__ import annotations

import logging
from typing import Any

from . import schema
from .const import DEFAULT_INTERVAL

_LOG = logging.getLogger(__name__)


def migriere(daten: Any) -> list[str]:
    """Die Beschreibung an Ort und Stelle auf die aktuellen Namen bringen.

    Liefert die Liste der Aenderungen in lesbarer Form (`pfad: alt → neu`) — leer, wenn
    nichts veraltet war. Der Konfigurator zeigt sie an, damit eine stille Umschreibung
    der eigenen Datei nicht still bleibt.
    """
    notizen: list[str] = []
    if not isinstance(daten, dict):
        return notizen
    vorgaben = daten.get("defaults") if isinstance(daten.get("defaults"), dict) else {}
    for i, panel in enumerate(_liste(daten.get("panels"))):
        if isinstance(panel, dict):
            _panel(panel, f"panels[{i}]", vorgaben, notizen)
    return notizen


# ==========================================================================
#  Die Struktur ablaufen — dieselbe Reihenfolge wie im Lader
# ==========================================================================
def _panel(panel: dict, pfad: str, vorgaben: dict, notizen: list[str]) -> None:
    # Der Bildtakt wird fuer die eine Umrechnung gebraucht, die es gibt (`wechsel_s`
    # in Sekunden -> `page_cycles` in Zyklen). Er wird genauso ermittelt wie im Lader,
    # sonst stuende nach der Migration eine andere Zahl in der Datei als die, mit der
    # die Anzeige bisher lief.
    interval = _zahl(panel.get("interval", vorgaben.get("interval")))

    for i, w in enumerate(_liste(panel.get("widgets"))):
        _widget(w, f"{pfad}.widgets[{i}]", notizen)

    for gi, gruppe in enumerate(_liste(panel.get("screen_groups"))):
        if not isinstance(gruppe, dict):
            continue
        gp = f"{pfad}.screen_groups[{gi}]"
        for si, screen in enumerate(_liste(gruppe.get("screens"))):
            if not isinstance(screen, dict):
                continue
            sp = f"{gp}.screens[{si}]"
            _schluessel(screen, "screen", sp, notizen, interval=interval)
            for i, w in enumerate(_liste(screen.get("widgets"))):
                _widget(w, f"{sp}.widgets[{i}]", notizen)
            # ⚠ Erst nach `_schluessel`: `seiten:` heisst jetzt `pages:`, und die Seiten
            # sollen auch dann durchlaufen werden, wenn sie eben erst umbenannt wurden.
            for pi_, seite in enumerate(_liste(screen.get("pages"))):
                if not isinstance(seite, dict):
                    continue
                pp = f"{sp}.pages[{pi_}]"
                _schluessel(seite, "seite", pp, notizen)
                for i, w in enumerate(_liste(seite.get("widgets"))):
                    _widget(w, f"{pp}.widgets[{i}]", notizen)


def _widget(w: Any, pfad: str, notizen: list[str]) -> None:
    if not isinstance(w, dict):
        return
    typ = w.get("type")
    if isinstance(typ, str) and typ in schema.TYP_UMBENANNT:
        w["type"] = schema.TYP_UMBENANNT[typ]      # Wert, nicht Schluessel: Platz bleibt
        notizen.append(f"{pfad}: type {typ} → {schema.TYP_UMBENANNT[typ]}")


# ==========================================================================
#  Einzelne Umbenennung
# ==========================================================================
def _schluessel(d: dict, gruppe: str, pfad: str, notizen: list[str], **ktx) -> None:
    tabelle = schema.UMBENANNT.get(gruppe, {})
    for alt in [k for k in tabelle if k in d]:
        neu, umrechner = tabelle[alt]
        wert = d[alt]
        if neu in d:
            # Beide da: genau wie im Lader gilt der neue Name; der alte wird nur
            # weggeraeumt. Etwas anderes waere eine stille Entscheidung darueber, was
            # gemeint war.
            del d[alt]
            notizen.append(f"{pfad}: {alt} entfernt ({neu} ist gesetzt)")
            continue
        if umrechner:
            try:
                wert = umrechner(wert, ktx)
            except (TypeError, ValueError) as e:
                _LOG.warning("%s: %r (veraltet) laesst sich nicht nach %r uebernehmen: "
                             "%s — bleibt stehen", pfad, alt, neu, e)
                continue
        _umbenennen(d, alt, neu, wert)
        notizen.append(f"{pfad}: {alt} → {neu}")


def _umbenennen(d: dict, alt: str, neu: str, wert: Any) -> None:
    """Schluessel umbenennen, ohne ihn zu verschieben und ohne seinen Kommentar."""
    stelle = list(d.keys()).index(alt)
    kommentar = None
    if hasattr(d, "ca"):                       # ruamel: Kommentare haengen am Schluessel
        kommentar = d.ca.items.pop(alt, None)
    del d[alt]
    if hasattr(d, "insert"):                   # CommentedMap kann positionstreu einfuegen
        d.insert(stelle, neu, wert)
        if kommentar is not None:
            d.ca.items[neu] = kommentar
    else:                                      # schlichtes dict: neu aufbauen
        rest = list(d.items())
        rest.insert(stelle, (neu, wert))
        d.clear()
        d.update(rest)


# ==========================================================================
#  Kleinkram
# ==========================================================================
def _liste(wert: Any) -> list:
    return wert if isinstance(wert, list) else []


def _zahl(wert: Any) -> float:
    try:
        return float(wert)
    except (TypeError, ValueError):
        return DEFAULT_INTERVAL
