"""Helligkeit — nur wenn die Beschreibung keine eigene Entität dafür nennt."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
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
    # ⚠ Steht in der YAML eine `brightness.entity`, gehoert die Helligkeit DORT hin.
    # Zwei Regler fuer denselben Wert waeren eine Einladung, sich gegenseitig zu
    # ueberschreiben.
    async_add_entities(
        Helligkeit(coordinator, pid)
        for pid, panel in coordinator.data.items()
        if panel.get("eigene_helligkeit")
    )


class Helligkeit(MatrixPanelEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "helligkeit"
    _attr_native_min_value = 1
    _attr_native_max_value = 255
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator, panel_id: str) -> None:
        super().__init__(coordinator, panel_id, "helligkeit")

    @property
    def native_value(self) -> float | None:
        return self.panel.get("helligkeit")

    async def async_set_native_value(self, value: float) -> None:
        await self.coordinator.api.setze_helligkeit(self._panel_id, int(value))
        await self.coordinator.async_request_refresh()
