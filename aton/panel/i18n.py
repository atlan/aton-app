"""Übersetzungen für die Oberfläche.

Eine neue Sprache ist **eine JSON-Datei** in `www/i18n/` — kein Codeeingriff. Die Schlüssel
sind flach und sprechend (`ui.speichern`, `schema.panel.host.label`), damit man beim
Übersetzen sieht, worum es geht, ohne den Quelltext danebenzulegen.

Rückfallkette: gewünschte Sprache → Deutsch → der Schlüssel selbst. Der letzte Schritt ist
Absicht: eine fehlende Übersetzung soll als `ui.irgendwas` sichtbar in der Oberfläche
stehen und nicht als leeres Feld. Ein leeres Feld sieht aus wie ein Fehler im Programm;
ein Schlüssel sagt, was fehlt.

Die deutschen Texte der Feldbeschreibungen stehen in `schema.py` und werden von
`tools/i18n_export.py` nach `de.json` gezogen — sie sind damit an einer Stelle gepflegt
und trotzdem für Übersetzer sichtbar.
"""
from __future__ import annotations

import glob
import json
import logging
import os

from .const import WWW_DIR

_LOG = logging.getLogger(__name__)

I18N_DIR = os.path.join(WWW_DIR, "i18n")
STANDARD = "de"


class Katalog:
    def __init__(self) -> None:
        self._sprachen: dict[str, dict[str, str]] = {}
        self._lade()

    def _lade(self) -> None:
        for pfad in sorted(glob.glob(os.path.join(I18N_DIR, "*.json"))):
            kuerzel = os.path.splitext(os.path.basename(pfad))[0].lower()
            try:
                with open(pfad, encoding="utf-8") as fh:
                    daten = json.load(fh)
                self._sprachen[kuerzel] = {k: str(v) for k, v in daten.items()
                                           if isinstance(v, (str, int, float))}
            except Exception as e:
                _LOG.warning("Sprachdatei %s unbrauchbar (%s: %s)",
                             pfad, type(e).__name__, e)
        _LOG.info("Sprachen: %s", ", ".join(sorted(self._sprachen)) or "keine")

    @property
    def sprachen(self) -> list[str]:
        return sorted(self._sprachen)

    def waehle(self, wunsch: str | None) -> str:
        """Sprachkürzel bestimmen. Akzeptiert auch 'de-DE' und Accept-Language-Listen."""
        if not wunsch:
            return STANDARD
        for teil in str(wunsch).split(","):
            kuerzel = teil.split(";")[0].strip().lower()
            if kuerzel in self._sprachen:
                return kuerzel
            kurz = kuerzel.split("-")[0]
            if kurz in self._sprachen:
                return kurz
        return STANDARD

    def text(self, schluessel: str, sprache: str = STANDARD) -> str:
        for s in (sprache, STANDARD):
            wert = self._sprachen.get(s, {}).get(schluessel)
            if wert:
                return wert
        return schluessel

    def alle(self, sprache: str) -> dict[str, str]:
        """Vollständiger Katalog mit Deutsch als Unterlage."""
        zusammen = dict(self._sprachen.get(STANDARD, {}))
        zusammen.update(self._sprachen.get(sprache, {}))
        return zusammen
