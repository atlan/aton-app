"""Zugriff auf die HTTP-Schnittstelle der App.

Die App laeuft als Add-on im selben Docker-Netz wie Home Assistant. Ihr Port ist NICHT
nach aussen veroeffentlicht (kein `ports:` im Manifest) — erreichbar ist sie nur von
Home Assistant aus, ueber ihren internen Hostnamen. Deshalb kommt die Schnittstelle
ohne eigene Anmeldung aus.
"""
from __future__ import annotations

from typing import Any

import aiohttp


class MatrixPanelError(Exception):
    """Die App antwortet nicht oder nicht wie erwartet."""


class MatrixPanelApi:
    def __init__(self, session: aiohttp.ClientSession, host: str, port: int) -> None:
        self._session = session
        self._basis = f"http://{host}:{port}"

    @property
    def basis(self) -> str:
        return self._basis

    async def _anfrage(self, methode: str, pfad: str, daten: dict | None = None) -> Any:
        try:
            async with self._session.request(
                methode, self._basis + pfad, json=daten,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as antwort:
                if antwort.status >= 400:
                    text = await antwort.text()
                    raise MatrixPanelError(f"HTTP {antwort.status}: {text[:200]}")
                if antwort.content_type == "application/json":
                    return await antwort.json()
                return await antwort.read()
        except MatrixPanelError:
            raise
        except Exception as err:  # Netzfehler, Zeitueberschreitung, kaputtes JSON
            raise MatrixPanelError(f"{type(err).__name__}: {err}") from err

    # -- lesen -------------------------------------------------------------
    async def panels(self) -> dict[str, Any]:
        return await self._anfrage("GET", "/api/panels")

    async def vorschau(self, panel: str, zoom: int = 4) -> bytes:
        return await self._anfrage("GET", f"/api/panel/{panel}/preview.png?zoom={zoom}")

    # -- schreiben ---------------------------------------------------------
    async def waehle_screen(self, panel: str, gruppe: str, wert: str) -> None:
        await self._anfrage("POST", f"/api/panel/{panel}/screen",
                            {"gruppe": gruppe, "wert": wert})

    async def vollbild(self, panel: str) -> None:
        await self._anfrage("POST", f"/api/panel/{panel}/vollbild")

    async def setze_helligkeit(self, panel: str, wert: int) -> None:
        await self._anfrage("POST", f"/api/panel/{panel}/helligkeit", {"wert": wert})

    async def notiz(self, panel: str, daten: dict) -> Any:
        return await self._anfrage("POST", f"/api/panel/{panel}/notify", daten)

    async def notiz_loeschen(self, panel: str, kennung: str | None = None,
                             kanal: str | None = None) -> None:
        await self._anfrage("POST", f"/api/panel/{panel}/notify_clear",
                            {"id": kennung, "channel": kanal})
