"""Diagnose je Anzeige — plus, was gerade wirklich zu sehen ist."""
from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable
from typing import Any

from homeassistant.components.sensor import (SensorEntity, SensorEntityDescription,
                                             SensorStateClass)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MatrixPanelCoordinator
from .entity import MatrixPanelEntity


@dataclass(frozen=True, kw_only=True)
class MatrixSensorDescription(SensorEntityDescription):
    wert: Callable[[dict[str, Any]], Any]


SENSOREN: tuple[MatrixSensorDescription, ...] = (
    MatrixSensorDescription(
        key="frames", translation_key="frames",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        wert=lambda p: p.get("frames"),
    ),
    MatrixSensorDescription(
        key="pixel", translation_key="pixel", native_unit_of_measurement="px",
        entity_category=EntityCategory.DIAGNOSTIC,
        wert=lambda p: p.get("pixel"),
    ),
    MatrixSensorDescription(
        key="bytes", translation_key="bytes", native_unit_of_measurement=UnitOfInformation.BYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
        wert=lambda p: p.get("bytes"),
    ),
    MatrixSensorDescription(
        key="fehler", translation_key="fehler", state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        wert=lambda p: p.get("fehler"),
    ),
    MatrixSensorDescription(
        key="letzter_fehler", translation_key="letzter_fehler",
        entity_category=EntityCategory.DIAGNOSTIC,
        # ⚠ Der Text wird von der App zurueckgenommen, sobald ein Bild sauber
        # durchlief. Eine Anzeige, die den aktuellen Zustand falsch behauptet, ist
        # schlimmer als gar keine.
        wert=lambda p: (p.get("letzter_fehler") or "—")[:255],
    ),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: MatrixPanelCoordinator = hass.data[DOMAIN][entry.entry_id]
    entitäten: list[SensorEntity] = []
    for pid, panel in coordinator.data.items():
        entitäten += [MatrixSensor(coordinator, pid, b) for b in SENSOREN]
        entitäten += [AktiverScreen(coordinator, pid, g["id"], g["name"])
                      for g in panel.get("gruppen", [])]
    async_add_entities(entitäten)


class MatrixSensor(MatrixPanelEntity, SensorEntity):
    entity_description: MatrixSensorDescription

    def __init__(self, coordinator, panel_id: str,
                 beschreibung: MatrixSensorDescription) -> None:
        super().__init__(coordinator, panel_id, beschreibung.key)
        self.entity_description = beschreibung

    @property
    def native_value(self) -> Any:
        return self.entity_description.wert(self.panel)


class AktiverScreen(MatrixPanelEntity, SensorEntity):
    """Was die Gruppe gerade zeigt — in Stellung Automatik nicht dasselbe wie die Auswahl."""

    _attr_icon = "mdi:eye"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, panel_id: str, gruppen_id: str, name: str) -> None:
        super().__init__(coordinator, panel_id, f"aktiv_{gruppen_id}")
        self._gruppen_id = gruppen_id
        self._attr_name = f"{name} aktiv"

    @property
    def native_value(self) -> str | None:
        for g in self.panel.get("gruppen", []):
            if g["id"] == self._gruppen_id:
                return g.get("aktiv")
        return None
