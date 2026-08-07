"""Einrichtung — im Normalfall ohne eine einzige Eingabe.

Die App meldet sich beim Supervisor an (`POST /discovery` mit `service: aton`).
Home Assistant benutzt den Dienstnamen **direkt als Integrations-Domain**
(`components/hassio/discovery.py`) und startet damit hier `async_step_hassio` — samt
Hostname und Port der App. Zu tippen ist dann nichts.

Der Handweg bleibt für den Fall, dass die App auf einem anderen Weg läuft.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.hassio import HassioServiceInfo

from .api import MatrixPanelApi, MatrixPanelError
from .const import CONF_HOST, CONF_PORT, DEFAULT_HOST, DEFAULT_PORT, DOMAIN


class MatrixPanelConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int | None = None

    async def _erreichbar(self, host: str, port: int) -> str | None:
        """Antwortet dort wirklich die App? Rueckgabe: Fehlerschluessel oder None."""
        api = MatrixPanelApi(async_get_clientsession(self.hass), host, port)
        try:
            daten = await api.panels()
        except MatrixPanelError:
            return "cannot_connect"
        if "panels" not in daten:
            return "unexpected_response"
        return None

    # -- von der App angemeldet -------------------------------------------
    async def async_step_hassio(self, discovery_info: HassioServiceInfo) -> ConfigFlowResult:
        cfg = discovery_info.config or {}
        self._host = cfg.get("host") or DEFAULT_HOST
        self._port = int(cfg.get("port") or DEFAULT_PORT)

        await self.async_set_unique_id(f"{self._host}:{self._port}")
        self._abort_if_unique_id_configured({CONF_HOST: self._host, CONF_PORT: self._port})

        self.context["title_placeholders"] = {"name": discovery_info.name or "Aton"}
        return await self.async_step_bestaetigen()

    async def async_step_bestaetigen(
            self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="bestaetigen",
                                        description_placeholders={"host": self._host})

        if fehler := await self._erreichbar(self._host, self._port):
            return self.async_abort(reason=fehler)
        return self.async_create_entry(title="Aton",
                                       data={CONF_HOST: self._host, CONF_PORT: self._port})

    # -- von Hand ----------------------------------------------------------
    async def async_step_user(
            self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        fehler: dict[str, str] = {}
        if user_input is not None:
            host, port = user_input[CONF_HOST], int(user_input[CONF_PORT])
            await self.async_set_unique_id(f"{host}:{port}")
            self._abort_if_unique_id_configured()
            if schluessel := await self._erreichbar(host, port):
                fehler["base"] = schluessel
            else:
                return self.async_create_entry(title="Aton", data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_HOST, default=DEFAULT_HOST): str,
                vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
            }),
            errors=fehler,
        )
