"""Vollbild anstoßen."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MatrixPanelCoordinator
from .entity import MatrixPanelEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: MatrixPanelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(Vollbild(coordinator, pid) for pid in coordinator.data)


class Vollbild(MatrixPanelEntity, ButtonEntity):
    """Erzwingt ein vollständiges Bild statt der üblichen Differenz.

    Nützlich nach einem WLED-Neustart: das Vollbild legt die Bildfläche an, räumt
    Altsegmente weg und färbt die Fläche einmal komplett — die App wartet sonst bis
    zum nächsten planmäßigen Anker.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "vollbild"

    def __init__(self, coordinator, panel_id: str) -> None:
        super().__init__(coordinator, panel_id, "vollbild")

    async def async_press(self) -> None:
        await self.coordinator.api.vollbild(self._panel_id)
        await self.coordinator.async_request_refresh()
