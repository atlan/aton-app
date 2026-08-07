"""Ein Abruf je Takt für alle Entitäten."""
from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MatrixPanelApi, MatrixPanelError
from .const import DOMAIN, UPDATE_INTERVAL

_LOGGER = logging.getLogger(__name__)


class MatrixPanelCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]]):
    """Holt `/api/panels` und legt es nach Anzeigen-ID ab.

    Ein Abruf versorgt sämtliche Entitäten aller Anzeigen — die App liefert alles in
    einer Antwort, und der Weg dorthin ist ein lokaler Docker-Hop.
    """

    def __init__(self, hass: HomeAssistant, api: MatrixPanelApi) -> None:
        super().__init__(
            hass, _LOGGER, name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL),
        )
        self.api = api
        self.quelle: str = "?"

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        try:
            roh = await self.api.panels()
        except MatrixPanelError as err:
            raise UpdateFailed(str(err)) from err

        self.quelle = roh.get("quelle", "?")
        return {p["id"]: p for p in roh.get("panels", [])}
