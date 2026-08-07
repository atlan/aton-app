"""Die Vorschau als Bild-Entität — das Matrixbild auf dem Dashboard."""
from __future__ import annotations

from homeassistant.components.image import ImageEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import MatrixPanelError
from .const import DOMAIN
from .coordinator import MatrixPanelCoordinator
from .entity import MatrixPanelEntity

ZOOM = 4


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry,
                            async_add_entities: AddEntitiesCallback) -> None:
    coordinator: MatrixPanelCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(Vorschau(hass, coordinator, pid) for pid in coordinator.data)


class Vorschau(MatrixPanelEntity, ImageEntity):
    """Das gerechnete Bild, vergrößert — so lässt sich die Matrix aus jedem Raum ansehen.

    Gezeigt wird, was die App RECHNET. Das ist fast immer identisch mit dem, was auf der
    Matrix steht, kann aber kurz auseinanderlaufen, wenn ein Sendevorgang verloren geht;
    die App holt das beim nächsten Vollbild nach.
    """

    _attr_content_type = "image/png"
    _attr_translation_key = "vorschau"

    def __init__(self, hass: HomeAssistant, coordinator, panel_id: str) -> None:
        MatrixPanelEntity.__init__(self, coordinator, panel_id, "vorschau")
        ImageEntity.__init__(self, hass)
        self._puffer: bytes | None = None
        self._stand: float = -1.0

    @property
    def image_last_updated(self):
        # Zeitstempel des letzten Renderlaufs der App; danach richtet sich, wann HA
        # das Bild neu holt.
        lauf = self.panel.get("letzter_lauf") or 0
        return dt_util.utc_from_timestamp(lauf) if lauf else None

    async def async_image(self) -> bytes | None:
        lauf = self.panel.get("letzter_lauf") or 0
        if self._puffer is not None and lauf == self._stand:
            return self._puffer
        try:
            self._puffer = await self.coordinator.api.vorschau(self._panel_id, ZOOM)
            self._stand = lauf
        except MatrixPanelError:
            return self._puffer      # lieber das letzte Bild als gar keins
        return self._puffer
