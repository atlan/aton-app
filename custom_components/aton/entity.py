"""Gemeinsame Basis: ein Gerät je Anzeige."""
from __future__ import annotations

from typing import Any

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import MatrixPanelCoordinator


class MatrixPanelEntity(CoordinatorEntity[MatrixPanelCoordinator]):
    """Alle Entitäten einer Anzeige hängen an EINEM Gerät.

    Das ist der Punkt, für den es die Integration überhaupt gibt: gebündelt unter einem
    Gerät, mit sprechenden Namen und einer Diagnose-Rubrik.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: MatrixPanelCoordinator, panel_id: str,
                 schluessel: str) -> None:
        super().__init__(coordinator)
        self._panel_id = panel_id
        self._attr_unique_id = f"{panel_id}_{schluessel}"

    @property
    def panel(self) -> dict[str, Any]:
        return self.coordinator.data.get(self._panel_id, {})

    @property
    def available(self) -> bool:
        return super().available and self._panel_id in self.coordinator.data

    @property
    def device_info(self) -> DeviceInfo:
        p = self.panel
        größe = p.get("size") or [0, 0]
        return DeviceInfo(
            identifiers={(DOMAIN, self._panel_id)},
            name=p.get("name") or self._panel_id,
            manufacturer="Aton",
            model=f"{größe[0]}x{größe[1]}",
            configuration_url=self.coordinator.api.basis,
            sw_version=None,
        )
