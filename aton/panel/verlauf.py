"""Verlaufsdaten aus Home Assistants Recorder — fuer `type: sparkline`.

★★ Warum ein Speicher und nicht ein Abruf im Widget: `Renderer.frame()` ist **synchron**
und laeuft in jedem Bildtakt, bei fuenf Sekunden also 720-mal pro Stunde. Eine Abfrage an
den Recorder ist um Groessenordnungen teurer als ein Blick in den Zustandsspiegel — sie
gehoert nicht in den Takt. Deshalb: eine Hintergrundaufgabe haelt die Kurven frisch, das
Zeichnen liest nur noch aus dem Speicher.

★ Und deshalb steht hier auch kein `await` im Zeichenweg. Wer das aendert, macht den
Renderer asynchron und damit jeden Aufrufer mit — die Vorschau im Konfigurator, den
Prueflauf, die Tests.

⚠ Ohne Verbindung oder vor dem ersten Lauf liefert `punkte()` eine **leere Liste**, nicht
etwa Nullen. Ein Diagramm auf der Grundlinie waere eine Aussage, die niemand gemacht hat;
das Widget zeichnet dann gar nichts und sagt es.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

_LOG = logging.getLogger(__name__)

#: Wie oft eine Kurve neu geholt wird. 300 s gegen einen 5-s-Bildtakt heisst: eine Abfrage
#: je 60 Bilder. Feiner braucht es nicht — eine Kurve ueber Stunden bewegt sich in fuenf
#: Minuten kaum, und der Recorder ist der teuerste Nachbar, den diese App hat.
INTERVALL_S = 300.0

#: Obergrenze der Stuetzstellen je Kurve. Breiter als die Anzeige braucht es nie: bei
#: 64 px Breite sind 64 Punkte schon einer je Spalte.
MAX_PUNKTE = 256


class VerlaufsSpeicher:
    """Haelt je (Entitaet, Stunden) eine Punktliste vor und frischt sie im Hintergrund auf."""

    def __init__(self, ha) -> None:
        self._ha = ha
        self._kurven: dict[tuple[str, int], list[float]] = {}
        self._gefragt: set[tuple[str, int]] = set()
        self._stand: dict[tuple[str, int], str] = {}

    # -- Lesen (synchron, aus dem Zeichenweg) ------------------------------
    def punkte(self, entity_id: str, stunden: int) -> list[float]:
        """Die Kurve, oder eine leere Liste, solange noch keine da ist."""
        return self._kurven.get((entity_id, stunden), [])

    def fehler(self, entity_id: str, stunden: int) -> str:
        """Warum es (noch) keine Kurve gibt — leer, wenn alles in Ordnung ist."""
        return self._stand.get((entity_id, stunden), "")

    def anmelden(self, entity_id: str, stunden: int) -> None:
        """Diese Kurve wird gebraucht. Mehrfach anmelden ist harmlos."""
        self._gefragt.add((entity_id, stunden))

    # -- Auffrischen (Hintergrundaufgabe) ----------------------------------
    async def run(self) -> None:
        await self._ha.bereit.wait()
        while True:
            for schluessel in sorted(self._gefragt):
                try:
                    await self._hole(*schluessel)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    # ⚠ Eine gescheiterte Kurve darf die anderen nicht aufhalten. Der Grund
                    # wird gemerkt, damit das Widget ihn zeigen kann, statt leer zu bleiben.
                    self._stand[schluessel] = f"{type(e).__name__}: {e}"
                    _LOG.warning("Verlauf %s (%d h) nicht geholt: %s", *schluessel, e)
            await asyncio.sleep(INTERVALL_S)

    async def _hole(self, entity_id: str, stunden: int) -> None:
        beginn = datetime.now(timezone.utc) - timedelta(hours=stunden)
        antwort = await self._ha.frage({
            "type": "history/history_during_period",
            "start_time": beginn.isoformat(),
            "entity_ids": [entity_id],
            # ⚠ Beides ist wichtig, nicht nur sparsam: ohne `minimal_response` und
            # `no_attributes` schickt HA je Zustandswechsel das ganze Attribut-Woerterbuch.
            # Bei einem Sensor mit langer Attributliste sind das schnell Megabyte fuer eine
            # Kurve, die aus ein paar hundert Zahlen besteht.
            "minimal_response": True,
            "no_attributes": True,
        })
        roh = (antwort or {}).get(entity_id) or []
        werte: list[float] = []
        for eintrag in roh:
            # HA liefert je nach Fassung `s` (minimal_response) oder `state`.
            zustand = eintrag.get("s", eintrag.get("state"))
            try:
                werte.append(float(zustand))
            except (TypeError, ValueError):
                continue        # unknown/unavailable/Text — ueberspringen, nicht raten
        self._kurven[(entity_id, stunden)] = _verdichten(werte, MAX_PUNKTE)
        self._stand[(entity_id, stunden)] = "" if werte else "keine Zahlenwerte im Zeitraum"


def _verdichten(werte: list[float], hoechstens: int) -> list[float]:
    """Auf hoechstens `hoechstens` Punkte eindampfen — durch MITTELN, nicht durch Wegwerfen.

    ⚠ Jeden n-ten Wert zu nehmen waere einfacher und falsch: bei einem Sensor, der auf
    jede Aenderung meldet, faellt so genau die Spitze weg, die man sehen wollte. Ein
    Mittel ueber den Eimer behaelt den Verlauf und glaettet nur das Zittern.
    """
    if len(werte) <= hoechstens:
        return werte
    eimer = len(werte) / hoechstens
    heraus = []
    for i in range(hoechstens):
        a, b = int(i * eimer), int((i + 1) * eimer)
        teil = werte[a:b] or werte[a:a + 1]
        heraus.append(sum(teil) / len(teil))
    return heraus
