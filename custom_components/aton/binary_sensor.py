"""Erreichbarkeit der Matrix und Zustand der Anzeige."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (BinarySensorDeviceClass,
                                                    BinarySensorEntity)
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
    entitäten: list[BinarySensorEntity] = []
    for pid in coordinator.data:
        entitäten.append(Erreichbar(coordinator, pid))
        entitäten.append(ZeigtAn(coordinator, pid))
    async_add_entities(entitäten)


class Erreichbar(MatrixPanelEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_translation_key = "erreichbar"

    def __init__(self, coordinator, panel_id: str) -> None:
        super().__init__(coordinator, panel_id, "erreichbar")

    @property
    def is_on(self) -> bool:
        return bool(self.panel.get("erreichbar"))


class ZeigtAn(MatrixPanelEntity, BinarySensorEntity):
    """Ob gerade gezeichnet wird — das Tor (WLED-Hauptschalter bzw. Stromschalter).

    Im Probelauf (`dry_run`) rechnet die App zwar, sendet aber nichts; das steht als
    Attribut daneben, damit niemand ein stehendes Bild für einen Fehler hält.
    """

    _attr_translation_key = "zeigt_an"

    def __init__(self, coordinator, panel_id: str) -> None:
        super().__init__(coordinator, panel_id, "zeigt_an")

    @property
    def is_on(self) -> bool:
        return bool(self.panel.get("an"))

    @property
    def extra_state_attributes(self) -> dict:
        return {"probelauf": bool(self.panel.get("probelauf"))}
