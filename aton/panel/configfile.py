"""Die Beschreibungsdatei lesen und schreiben — ohne die Kommentare zu verlieren.

★ Der Punkt, an dem ein Konfigurator sonst Schaden anrichtet: er liest YAML, macht daraus
Datenstrukturen, schreibt sie zurück — und alle Kommentare sind weg. In dieser Datei
stecken aber die Begründungen, warum ein Tor einen Rückfall hat oder warum der Zählerstand
ein breiteres Feld bekommt. Die sind mehr wert als die Bequemlichkeit.

Deshalb `ruamel.yaml` im Round-Trip-Modus und ein **Verschmelzen in die vorhandene
Struktur** statt eines Neuschreibens: unveränderte Stellen behalten ihre Kommentare, weil
sie gar nicht angefasst werden.

⚠ Ehrliche Grenze: Kommentare an einem LISTENEINTRAG hängen an dessen Position. Wird ein
Eintrag eingefügt oder verschoben, wandert der Kommentar nicht mit — er bleibt an der
Stelle. Beim Löschen des letzten Eintrags geht sein Kommentar verloren. Kommentare an
Schlüsseln überleben.
"""
from __future__ import annotations

import logging
import os
import shutil
import tempfile
from datetime import datetime
from io import StringIO
from typing import Any

from ruamel.yaml import YAML

_LOG = logging.getLogger(__name__)

#: Unterordner neben der Beschreibungsdatei, in dem die Sicherungen landen.
SICHERUNGSORDNER = "aton_sicherungen"
#: Bis 0.8.0 hiess der Ordner nach der alten Kennung. Wird beim ersten Schreiben
#: umgezogen — sonst laegen die alten Sicherungen fuer immer daneben und die
#: Aufraeumung faende sie nie wieder.
ALTER_ORDNER = "matrix_panel_sicherungen"

#: Wieviele Sicherungen liegenbleiben. Bewusst fest verdrahtet und nicht in der
#: Beschreibungsdatei einstellbar: eine Einstellung, die man einmal setzt und nie wieder
#: anfasst, ist eine Einstellung zuviel. Zwanzig deckt jede Bearbeitungssitzung ab.
BEHALTEN = 20


class SchreibFehler(Exception):
    pass


def _yaml() -> YAML:
    """⚠ Die Einrueckung MUSS zum Stil der Datei passen — sonst gehen Kommentare kaputt.

    Gemessen, nicht vermutet: mit `sequence=2, offset=0` rutschen Listeneintraege von
    Spalte 6 auf Spalte 2, waehrend die Kommentare darueber auf Spalte 6 stehenbleiben.
    Beim naechsten Einlesen haengt der Kommentar dadurch am falschen Knoten, und der
    uebernaechste Schreibvorgang zieht ihn zu einer Zeile zusammen und bricht ihn um —
    aus zwei Kommentarzeilen wird eine Kommentarzeile plus eine Zeile ohne `#`.
    Der Fehler zeigt sich also erst beim ZWEITEN Speichern; ein einzelner Test haette
    ihn nicht gefunden.

    `sequence=4, offset=2` erzeugt den ueblichen Stil (`  - eintrag`), der auch in der
    mitgelieferten Beispieldatei steht. `width` gross genug, damit nichts umbrochen wird:
    ein Umbruch trifft auch Kommentare und verliert dort das `#`.
    """
    y = YAML()
    y.preserve_quotes = True
    y.width = 4096
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def lese(pfad: str) -> tuple[Any, float, str]:
    """Rueckgabe: (Daten mit Kommentaren, mtime, Rohtext)."""
    with open(pfad, encoding="utf-8") as fh:
        text = fh.read()
    daten = _yaml().load(text)
    return daten, os.path.getmtime(pfad), text


def als_text(daten: Any) -> str:
    puffer = StringIO()
    _yaml().dump(daten, puffer)
    return puffer.getvalue()


def verschmelze(ziel: Any, quelle: Any) -> Any:
    """`quelle` in `ziel` einarbeiten und dabei alles Unveraenderte in Ruhe lassen.

    Genau dieses In-Ruhe-Lassen erhaelt die Kommentare: ruamel haengt sie an die
    vorhandenen Knoten, und wer die nicht ersetzt, verliert nichts.
    """
    if isinstance(ziel, dict) and isinstance(quelle, dict):
        # ⚠ Der Weg durch den Browser fuehrt ueber JSON, und dort sind Objektschluessel
        # IMMER Zeichenketten. Aus `steps: {337.5: wind_n}` wuerde beim Zurueckschreiben
        # sonst `steps: {"337.5": wind_n}` — funktional gleich (die Pruefung wandelt mit
        # float()), aber die Datei wuerde bei JEDEM Speichern still umgeschrieben.
        # Deshalb: passt ein Schluessel in Textform zu einem vorhandenen, gilt der
        # vorhandene mit seinem urspruenglichen Typ.
        nach_text = {str(k): k for k in ziel}
        umgesetzt = {nach_text.get(str(k), k): v for k, v in quelle.items()}

        for schluessel in [k for k in ziel if k not in umgesetzt]:
            del ziel[schluessel]
        for schluessel, wert in umgesetzt.items():
            if schluessel in ziel:
                ziel[schluessel] = verschmelze(ziel[schluessel], wert)
            else:
                ziel[schluessel] = wert
        return ziel

    if isinstance(ziel, list) and isinstance(quelle, list):
        for i in range(min(len(ziel), len(quelle))):
            ziel[i] = verschmelze(ziel[i], quelle[i])
        while len(ziel) > len(quelle):
            ziel.pop()
        for i in range(len(ziel), len(quelle)):
            ziel.append(quelle[i])
        return ziel

    return quelle


def schreibe(pfad: str, daten: Any, erwartete_mtime: float | None = None) -> str:
    """Sichern, schreiben, zurueckmelden wohin gesichert wurde.

    ⚠ `erwartete_mtime` ist die Wacht gegen gleichzeitiges Bearbeiten: wer die Datei
    nebenher im Studio Code Server aendert, soll seine Arbeit nicht stillschweigend
    verlieren.

    Geschrieben wird ueber eine Zwischendatei im selben Verzeichnis und `os.replace` —
    damit liegt dort nie eine halbe Datei, auch nicht bei einem Stromausfall mitten im
    Vorgang.
    """
    if erwartete_mtime is not None and os.path.exists(pfad):
        ist = os.path.getmtime(pfad)
        if abs(ist - erwartete_mtime) > 0.001:
            raise SchreibFehler(
                "Die Datei wurde zwischenzeitlich ausserhalb des Konfigurators geaendert.")

    ordner = os.path.dirname(pfad) or "."
    stempel = datetime.now().strftime("%Y%m%d-%H%M%S")
    sicherung = os.path.join(_sicherungsordner(pfad),
                             f"{os.path.basename(pfad)}.bak-{stempel}")
    if os.path.exists(pfad):
        shutil.copy2(pfad, sicherung)

    text = als_text(daten)
    fd, temp = tempfile.mkstemp(dir=ordner, prefix=".aton_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp, pfad)
    except Exception:
        if os.path.exists(temp):
            os.unlink(temp)
        raise

    _LOG.info("Beschreibung geschrieben (%d Bytes), Sicherung: %s",
              len(text.encode("utf-8")), os.path.basename(sicherung))
    return sicherung


def _sicherungsordner(pfad: str) -> str:
    """Unterordner neben der Beschreibungsdatei, in dem die Sicherungen liegen.

    ★ Warum nicht daneben: die Beschreibung liegt in `/config`, also mitten im
    Konfigurationsordner von Home Assistant. Zwanzig `aton.yaml.bak-…` machen den
    Dateibrowser dort unbrauchbar. Ein eigener Ordner haelt die Sicherungen beisammen,
    ohne dass jemand sie suchen muss.

    Der Ordner wird bei Bedarf angelegt; er liegt bewusst NEBEN der Datei und nicht in
    `/tmp`, damit die Sicherungen den Neustart der App ueberleben.
    """
    basis = os.path.dirname(pfad) or "."
    ordner = os.path.join(basis, SICHERUNGSORDNER)
    os.makedirs(ordner, exist_ok=True)
    # Umbenennung 0.9.0: alte Sicherungen mitnehmen, statt sie verwaisen zu lassen —
    # die Aufraeumung sucht nur im aktuellen Ordner.
    alt = os.path.join(basis, ALTER_ORDNER)
    if os.path.isdir(alt):
        umgezogen = 0
        for f in sorted(os.listdir(alt)):
            try:
                shutil.move(os.path.join(alt, f), os.path.join(ordner, f))
                umgezogen += 1
            except OSError:
                pass
        try:
            os.rmdir(alt)
        except OSError:
            pass
        if umgezogen:
            _LOG.info("%d Sicherung(en) von %s/ nach %s/ umgezogen",
                      umgezogen, ALTER_ORDNER, SICHERUNGSORDNER)
    return ordner


def sicherungen_umziehen(pfad: str) -> int:
    """Sicherungen aus frueheren Fassungen in den Unterordner holen.

    Bis 0.5.0 lagen sie direkt neben der Beschreibungsdatei. Ohne diesen Umzug blieben
    sie dort fuer immer liegen — die Aufraeumung wuerde sie nicht mehr finden und nie
    wieder anfassen.
    """
    alt = os.path.dirname(pfad) or "."
    name = os.path.basename(pfad)
    ziel = _sicherungsordner(pfad)
    umgezogen = 0
    for f in sorted(os.listdir(alt)):
        if not f.startswith(name + ".bak-"):
            continue
        try:
            shutil.move(os.path.join(alt, f), os.path.join(ziel, f))
            umgezogen += 1
        except OSError:
            pass
    if umgezogen:
        _LOG.info("%d Sicherung(en) nach %s/ umgezogen", umgezogen, SICHERUNGSORDNER)
    return umgezogen


def sicherungen_aufraeumen(pfad: str, behalten: int = BEHALTEN) -> int:
    """Alte Sicherungen wegwerfen — sonst waechst der Ordner unbegrenzt.

    ⚠ Sortiert wird nach dem Dateinamen, nicht nach der Aenderungszeit: der Zeitstempel
    im Namen (`…bak-JJJJMMTT-HHMMSS`) ist fest, die mtime dagegen kopiert `copy2` von der
    Quelldatei — die kann aelter sein als die Sicherung. Nach mtime zu sortieren wuerfe
    also unter Umstaenden die falsche weg.
    """
    ordner = _sicherungsordner(pfad)
    name = os.path.basename(pfad)
    alle = sorted(f for f in os.listdir(ordner) if f.startswith(name + ".bak-"))
    weg = alle[:-behalten] if len(alle) > behalten else []
    for f in weg:
        try:
            os.unlink(os.path.join(ordner, f))
        except OSError:
            pass
    if weg:
        _LOG.info("%d alte Sicherung(en) weggeraeumt, %d bleiben liegen",
                  len(weg), len(alle) - len(weg))
    return len(weg)
