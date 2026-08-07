"""Sich beim Supervisor anmelden, damit Home Assistant die App von selbst findet.

Der Supervisor nimmt einen **frei gewaehlten** Dienstnamen entgegen (`ATTR_SERVICE: str`
in `supervisor/discovery/validate.py`, keine feste Liste), und Home Assistant benutzt
diesen Namen **direkt als Integrations-Domain**
(`homeassistant/components/hassio/discovery.py`: `async_create_flow(hass, data.service, …)`).

Meldet die App also `service: "aton"` an, taucht die Begleit-Integration in HA
als „gefunden" auf — mit Hostname und Port im Gepaeck. Der Benutzer klickt einmal auf
Einrichten und muss nichts eintippen.

⚠ Der Dienstname MUSS in `config.yaml` unter `discovery:` stehen, sonst weist der
Supervisor die Anmeldung ab.

⚠ **`GET /discovery` ist Apps NICHT erlaubt** (401) — nur Home Assistant selbst darf die
Liste lesen; `POST` dagegen schon. Ein Aufraeumen alter Eintraege ueber die Liste scheitert
also. Es ist auch unnoetig: der Supervisor dedupliziert von sich aus (`discovery/__init__.py`,
`send()`: gleiche App + Dienst + Konfiguration -> bestehende Nachricht).

⚠ **Beim Beenden wird NICHT abgemeldet.** HA entfernt zu einer geloeschten Anmeldung unter
Umstaenden den Konfigurationseintrag — bei jedem App-Neustart die Einrichtung des Benutzers
wegzuwerfen waere ein schlechter Tausch fuer einen aufgeraeumten Datensatz.
"""
from __future__ import annotations

import logging

import aiohttp

from .const import SUPERVISOR_TOKEN, SUPERVISOR_URL

_LOG = logging.getLogger(__name__)

DIENST = "aton"


class Anmeldung:
    """Meldet die App an und raeumt beim Beenden wieder auf."""

    def __init__(self, port: int):
        self._port = port
        self._uuid: str | None = None
        self._kopf = {"Authorization": f"Bearer {SUPERVISOR_TOKEN}"}

    async def _api(self, session, methode: str, pfad: str, daten: dict | None = None):
        async with session.request(methode, SUPERVISOR_URL + pfad, json=daten,
                                   headers=self._kopf,
                                   timeout=aiohttp.ClientTimeout(total=15)) as a:
            a.raise_for_status()
            return (await a.json()).get("data") if a.content_length else None

    async def anmelden(self) -> None:
        try:
            async with aiohttp.ClientSession() as s:
                selbst = await self._api(s, "GET", "/addons/self/info")
                host = selbst.get("hostname")
                antwort = await self._api(s, "POST", "/discovery", {
                    "service": DIENST,
                    "config": {"host": host, "port": self._port},
                })
                self._uuid = (antwort or {}).get("uuid")
                _LOG.info("Bei Home Assistant angemeldet als %s (%s:%s)",
                          DIENST, host, self._port)
        except Exception as e:
            # Ohne Anmeldung laesst sich die Integration weiterhin von Hand einrichten.
            _LOG.warning("Selbstanmeldung nicht moeglich (%s: %s) — die Integration kann "
                         "trotzdem von Hand hinzugefuegt werden", type(e).__name__, e)

