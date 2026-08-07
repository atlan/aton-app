"""Aton — Begleit-Integration zur gleichnamigen App.

Die App rendert und sendet; diese Integration macht daraus in Home Assistant ein Gerät
mit Auswahl, Diagnose, Knopf, Helligkeitsregler und Vorschaubild — und stellt die
Dienste `aton.notify` / `.notify_clear` bereit.
"""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceEntry

from .api import MatrixPanelApi, MatrixPanelError
from .const import (ATTR_DURATION, ATTR_ID, ATTR_LEVEL, ATTR_PANEL, ATTR_PRIORITY,
                    ATTR_TEXT, CONF_HOST, CONF_PORT, DOMAIN, SERVICE_NOTIFY,
                    SERVICE_NOTIFY_CLEAR)
from .coordinator import MatrixPanelCoordinator

_LOGGER = logging.getLogger(__name__)

PLATTFORMEN: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]

NOTIFY_SCHEMA = vol.Schema({
    vol.Required(ATTR_TEXT): cv.string,
    vol.Optional(ATTR_LEVEL, default="info"): vol.In(["info", "warning"]),
    vol.Optional(ATTR_DURATION, default=30): vol.All(vol.Coerce(float), vol.Range(min=0)),
    vol.Optional(ATTR_ID): cv.string,
    vol.Optional(ATTR_PRIORITY): vol.All(vol.Coerce(int), vol.Range(min=1, max=9)),
    vol.Optional(ATTR_PANEL): cv.string,
})

NOTIFY_CLEAR_SCHEMA = vol.Schema({
    vol.Optional(ATTR_ID): cv.string,
    vol.Optional(ATTR_PANEL): cv.string,
})


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    api = MatrixPanelApi(async_get_clientsession(hass),
                         entry.data[CONF_HOST], entry.data[CONF_PORT])
    coordinator = MatrixPanelCoordinator(hass, api)
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATTFORMEN)
    _dienste_anmelden(hass)
    return True


async def async_remove_config_entry_device(hass: HomeAssistant, entry: ConfigEntry,
                                           device: DeviceEntry) -> bool:
    """Darf dieses Geraet geloescht werden?

    ★ Ohne diese Funktion bietet Home Assistant das Loeschen gar nicht erst an
    („Config entry does not support device removal"). Wer die Kennung einer Anzeige
    aendert oder eine Anzeige aus der Beschreibung nimmt, behaelt das alte Geraet dann
    fuer immer in der Uebersicht — leer, aber sichtbar, und von Hand nicht wegzubekommen.

    Erlaubt wird es genau dann, wenn die App die Anzeige **nicht mehr kennt**. Ein Geraet
    zu einer laufenden Anzeige bleibt geschuetzt, sonst loescht man sich versehentlich die
    Entitaeten weg, an denen Automationen und Firmware haengen.
    """
    coordinator: MatrixPanelCoordinator = hass.data[DOMAIN][entry.entry_id]
    bekannt = set(coordinator.data or {})
    eigene = {kennung for bereich, kennung in device.identifiers if bereich == DOMAIN}
    return not (eigene & bekannt)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    entladen = await hass.config_entries.async_unload_platforms(entry, PLATTFORMEN)
    if entladen:
        hass.data[DOMAIN].pop(entry.entry_id)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_NOTIFY)
            hass.services.async_remove(DOMAIN, SERVICE_NOTIFY_CLEAR)
    return entladen


def _dienste_anmelden(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_NOTIFY):
        return

    def _ziele(panel: str | None) -> list[tuple[MatrixPanelCoordinator, str]]:
        """Welche Anzeigen sind gemeint? Ohne Angabe: alle."""
        gefunden = [
            (co, pid)
            for co in hass.data[DOMAIN].values()
            for pid in co.data
            if panel in (None, pid)
        ]
        if not gefunden:
            raise HomeAssistantError(
                f"Keine Anzeige {panel!r} gefunden" if panel else "Keine Anzeige vorhanden")
        return gefunden

    async def notify(call: ServiceCall) -> None:
        daten = {k: v for k, v in call.data.items() if k != ATTR_PANEL}
        for coordinator, pid in _ziele(call.data.get(ATTR_PANEL)):
            try:
                await coordinator.api.notiz(pid, daten)
            except MatrixPanelError as err:
                raise HomeAssistantError(f"Meldung an {pid} gescheitert: {err}") from err
            await coordinator.async_request_refresh()

    async def notify_clear(call: ServiceCall) -> None:
        for coordinator, pid in _ziele(call.data.get(ATTR_PANEL)):
            try:
                await coordinator.api.notiz_loeschen(pid, call.data.get(ATTR_ID))
            except MatrixPanelError as err:
                raise HomeAssistantError(f"Loeschen an {pid} gescheitert: {err}") from err
            await coordinator.async_request_refresh()

    hass.services.async_register(DOMAIN, SERVICE_NOTIFY, notify, schema=NOTIFY_SCHEMA)
    hass.services.async_register(DOMAIN, SERVICE_NOTIFY_CLEAR, notify_clear,
                                 schema=NOTIFY_CLEAR_SCHEMA)
