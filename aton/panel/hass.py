"""Anbindung an Home Assistant ueber die WebSocket-API.

Die App haelt einen **vollstaendigen Zustandsspiegel** im Speicher: einmal `get_states`,
danach jedes `state_changed`-Ereignis. Das kostet ein paar Megabyte und erspart dafuer
jede Abfrage zur Renderzeit — ein Frame liest 50 Werte aus einem dict statt 50 Mal ueber
das Netz zu gehen. Ausserdem muss niemand vorher aufzaehlen, welche Entitaeten eine
Vorlage (Template) benutzen wird.

Verbindungsabbrueche sind der Normalfall (HA-Neustart). Deshalb: Wiederverbindung mit
wachsendem Abstand, und `verbunden` sagt jederzeit, ob die Werte aktuell sind. Ein Frame
aus veralteten Werten waere schlimmer als gar keiner.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable

import aiohttp

from .const import HA_WS_URL, SUPERVISOR_TOKEN

_LOG = logging.getLogger(__name__)


class HomeAssistant:
    def __init__(self, url: str = HA_WS_URL, token: str = SUPERVISOR_TOKEN):
        self._url = url
        self._token = token
        self._states: dict[str, dict[str, Any]] = {}
        self._msg_id = 0
        self.verbunden = False
        # Die offene Verbindung festhalten — nur damit lassen sich Dienste rufen.
        # Wird beim Verbindungsabbruch wieder auf None gesetzt, damit ein Aufruf
        # ins Leere sichtbar scheitert statt still zu verschwinden.
        self._ws = None
        self.bereit = asyncio.Event()
        self._horcher: list[Callable[[str], None]] = []

    # -- Lesezugriff -------------------------------------------------------
    def state(self, entity_id: str) -> str | None:
        eintrag = self._states.get(entity_id)
        return eintrag["state"] if eintrag else None

    def attr(self, entity_id: str, name: str) -> Any:
        eintrag = self._states.get(entity_id)
        return eintrag["attributes"].get(name) if eintrag else None

    def existiert(self, entity_id: str) -> bool:
        return entity_id in self._states

    @property
    def anzahl(self) -> int:
        return len(self._states)

    def bei_aenderung(self, rueckruf: Callable[[str], None]) -> None:
        """Wird mit der Entity-ID gerufen, sobald sich ein Zustand aendert."""
        self._horcher.append(rueckruf)

    # -- Verbindung --------------------------------------------------------
    async def run(self) -> None:
        wartezeit = 1.0
        while True:
            try:
                await self._sitzung()
                wartezeit = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as e:
                _LOG.warning("HA-Verbindung verloren (%s: %s) — neuer Versuch in %.0fs",
                             type(e).__name__, e, wartezeit)
            finally:
                self.verbunden = False
                self.bereit.clear()
            await asyncio.sleep(wartezeit)
            wartezeit = min(wartezeit * 2, 60.0)

    async def _sitzung(self) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(self._url, heartbeat=30) as ws:
                erste = await ws.receive_json()
                if erste.get("type") != "auth_required":
                    raise RuntimeError(f"unerwartete Begruessung: {erste}")
                await ws.send_json({"type": "auth", "access_token": self._token})
                antwort = await ws.receive_json()
                if antwort.get("type") != "auth_ok":
                    raise RuntimeError(f"Anmeldung abgelehnt: {antwort}")

                await self._sende(ws, {"type": "subscribe_events",
                                       "event_type": "state_changed"})
                zustands_id = await self._sende(ws, {"type": "get_states"})

                self.verbunden = True
                self._ws = ws
                _LOG.info("Mit Home Assistant verbunden (%s)", self._url)

                async for nachricht in ws:
                    if nachricht.type is not aiohttp.WSMsgType.TEXT:
                        continue
                    daten = nachricht.json()
                    if daten.get("type") == "result" and daten.get("id") == zustands_id:
                        self._uebernehme_alle(daten.get("result") or [])
                    elif daten.get("type") == "event":
                        self._uebernehme_aenderung(daten.get("event") or {})
                    elif daten.get("type") == "result" and not daten.get("success", True):
                        _LOG.warning("HA meldet Fehler: %s", daten.get("error"))
        self._ws = None
        raise RuntimeError("WebSocket geschlossen")

    async def rufe_dienst(self, entity_id: str, dienst: str,
                          daten: dict | None = None) -> bool:
        """Einen HA-Dienst aufrufen. Domain kommt aus der Entitaets-ID.

        ⚠ Die Domain darf NICHT fest verdrahtet werden — dieselbe Falle steckte in Osiris
        (`input_select` hart im Pfad), und der Knopf war danach wirkungslos, ohne dass
        irgendwo ein Fehler stand. `script.x` braucht `script/turn_on`, `switch.x`
        braucht `switch/turn_on`.

        Die App liest sonst nur; das hier ist der einzige schreibende Weg. Bewusst eng
        gehalten: eine Entitaet, ein Dienst, keine freie Nutzlast von aussen.
        """
        if self._ws is None:
            _LOG.warning("Dienstaufruf %s.%s: keine WebSocket-Verbindung", entity_id, dienst)
            return False
        domain = entity_id.split(".", 1)[0]
        nutzlast = {"type": "call_service", "domain": domain, "service": dienst,
                    "target": {"entity_id": entity_id}}
        if daten:
            nutzlast["service_data"] = daten
        try:
            await self._sende(self._ws, nutzlast)
        except Exception as e:
            _LOG.warning("Dienstaufruf %s.%s gescheitert: %s", entity_id, dienst, e)
            return False
        _LOG.info("Dienst gerufen: %s.%s auf %s", domain, dienst, entity_id)
        return True

    async def _sende(self, ws, nutzlast: dict) -> int:
        self._msg_id += 1
        nutzlast = dict(nutzlast, id=self._msg_id)
        await ws.send_json(nutzlast)
        return self._msg_id

    # -- Zustandsspiegel ---------------------------------------------------
    def _uebernehme_alle(self, zustaende: list[dict]) -> None:
        self._states = {z["entity_id"]: {"state": z["state"],
                                         "attributes": z.get("attributes") or {}}
                        for z in zustaende}
        _LOG.info("Zustandsspiegel gefuellt: %d Entitaeten", len(self._states))
        self.bereit.set()

    def _uebernehme_aenderung(self, ereignis: dict) -> None:
        daten = ereignis.get("data") or {}
        eid = daten.get("entity_id")
        neu = daten.get("new_state")
        if not eid:
            return
        if neu is None:
            self._states.pop(eid, None)
        else:
            self._states[eid] = {"state": neu["state"],
                                 "attributes": neu.get("attributes") or {}}
        for rueckruf in self._horcher:
            try:
                rueckruf(eid)
            except Exception:
                _LOG.exception("Horcher auf %s ist gestolpert", eid)
