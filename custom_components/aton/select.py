"""Auswahl je Screen-Gruppe: Automatik oder ein fester Screen."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AUTOMATIK, DOMAIN
from .coordinator import MatrixPanelCoordinator
from .entity import MatrixPanelEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: MatrixPanelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        ScreenAuswahl(coordinator, pid, g["id"], g["name"])
        for pid, panel in coordinator.data.items()
        for g in panel.get("gruppen", [])
    )


class ScreenAuswahl(MatrixPanelEntity, SelectEntity):
    _attr_icon = "mdi:view-carousel"

    def __init__(self, coordinator, panel_id: str, gruppen_id: str, name: str) -> None:
        super().__init__(coordinator, panel_id, f"select_{gruppen_id}")
        self._gruppen_id = gruppen_id
        self._attr_name = name
        self._attr_translation_key = None

    @property
    def _gruppe(self) -> dict:
        for g in self.panel.get("gruppen", []):
            if g["id"] == self._gruppen_id:
                return g
        return {}

    @property
    def options(self) -> list[str]:
        return [AUTOMATIK] + list(self._gruppe.get("screens", []))

    @property
    def current_option(self) -> str | None:
        return self._gruppe.get("vorwahl")

    @property
    def extra_state_attributes(self) -> dict:
        # In Stellung „Automatik" ist die Auswahl nicht dasselbe wie das, was zu sehen
        # ist — deshalb steht der wirklich aktive Screen als Attribut daneben.
        return {"aktiver_screen": self._gruppe.get("aktiv")}

    async def async_select_option(self, option: str) -> None:
        await self.coordinator.api.waehle_screen(self._panel_id, self._gruppen_id, option)
        await self.coordinator.async_request_refresh()
