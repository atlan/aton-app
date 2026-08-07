"""Vorlagen (Jinja) gegen den eigenen Zustandsspiegel auswerten.

⚠ **Das ist HAs Vorlagensprache in Teilen, nicht vollstaendig.** Bereitgestellt sind die
Funktionen, die in Anzeige-Bedingungen praktisch vorkommen: `states`, `state_attr`,
`is_state`, `is_state_attr`, `has_value`, `now`. Was HA sonst noch kann (Geraete-Aufloesung,
`expand`, `area_*`, Verlaufsdaten) fehlt hier — wer das braucht, baut in HA einen
Template-Sensor und liest den hier aus.

Ausgewertet wird lokal, ohne Rueckfrage an HA: eine Bedingung pro Screen und Frame kostet
so nichts.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Protocol

import jinja2

from .const import UNAVAILABLE_STATES

_LOG = logging.getLogger(__name__)


class Zustandsquelle(Protocol):
    def state(self, entity_id: str) -> str | None: ...
    def attr(self, entity_id: str, name: str) -> Any: ...


class TemplateError(Exception):
    pass


class TemplateEngine:
    def __init__(self, quelle: Zustandsquelle):
        self._quelle = quelle
        self._env = jinja2.Environment(autoescape=False, undefined=jinja2.Undefined)
        self._env.globals.update({
            "states": self._states,
            "state_attr": self._state_attr,
            "is_state": self._is_state,
            "is_state_attr": self._is_state_attr,
            "has_value": self._has_value,
            "now": datetime.now,
            "utcnow": datetime.utcnow,
        })
        self._cache: dict[str, jinja2.Template] = {}

    # -- HA-aehnliche Funktionen ------------------------------------------
    def _states(self, entity_id: str) -> str:
        wert = self._quelle.state(entity_id)
        return "unknown" if wert is None else wert

    def _state_attr(self, entity_id: str, name: str) -> Any:
        return self._quelle.attr(entity_id, name)

    def _is_state(self, entity_id: str, wert: Any) -> bool:
        ist = self._quelle.state(entity_id)
        if isinstance(wert, (list, tuple)):
            return ist in [str(w) for w in wert]
        return ist == str(wert)

    def _is_state_attr(self, entity_id: str, name: str, wert: Any) -> bool:
        return self._quelle.attr(entity_id, name) == wert

    def _has_value(self, entity_id: str) -> bool:
        return self._quelle.state(entity_id) not in UNAVAILABLE_STATES

    # -- Auswertung --------------------------------------------------------
    def _kompiliere(self, vorlage: str) -> jinja2.Template:
        if vorlage not in self._cache:
            try:
                self._cache[vorlage] = self._env.from_string(vorlage)
            except jinja2.TemplateSyntaxError as e:
                raise TemplateError(f"Vorlage fehlerhaft (Zeile {e.lineno}): {e.message}") from None
        return self._cache[vorlage]

    def render(self, vorlage: str) -> str:
        try:
            return self._kompiliere(vorlage).render().strip()
        except TemplateError:
            raise
        except Exception as e:
            raise TemplateError(f"{type(e).__name__}: {e}") from None

    def truthy(self, vorlage: str) -> bool:
        """Bedingung auswerten. Alles ausser den ueblichen Ja-Woertern ist Nein."""
        return self.render(vorlage).strip().lower() in ("true", "on", "yes", "1", "wahr", "ja")
