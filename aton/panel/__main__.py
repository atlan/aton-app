"""Einstiegspunkt der App."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys

import aiohttp

from . import configfile, web
from .config import AppCfg, ConfigError, lade
from .const import HA_CONFIG_DIR, INGRESS_PORT, OPTIONS_PATH, anzeige_pfad
from .discovery import Anmeldung
from .display import Display
from .fonts import FontRegistry
from .hass import HomeAssistant
from .i18n import Katalog
from .icons import IconRegistry

_LOG = logging.getLogger("panel")


class AppState:
    """Was die Oberflaeche zu sehen bekommt — und was der Konfigurator veraendert."""

    def __init__(self, cfg: AppCfg, pfad: str, ha, fonts, icons, katalog):
        self.cfg = cfg
        self.pfad = pfad
        self.ha = ha
        self.fonts = fonts
        self.icons = icons
        self.katalog = katalog
        self.displays: dict[str, Display] = {}
        self.session = None
        self._aufgaben: dict[str, asyncio.Task] = {}
        # Warum gerade keine Anzeige laeuft. Die Oberflaeche zeigt das an — sonst steht
        # man vor einer leeren Betriebsansicht und haelt die App fuer kaputt.
        self.ladefehler: str = ""

    def starte_displays(self) -> None:
        for pid, d in self.displays.items():
            self._aufgaben[pid] = asyncio.create_task(d.run(self.session),
                                                      name=f"panel:{pid}")

    async def _stoppe_displays(self) -> None:
        for a in self._aufgaben.values():
            a.cancel()
        if self._aufgaben:
            await asyncio.gather(*self._aufgaben.values(), return_exceptions=True)
        self._aufgaben.clear()

    async def neu_laden(self) -> bool:
        """Beschreibung neu einlesen und die Anzeigen neu aufbauen — ohne App-Neustart.

        ⚠ Die Anzeigen werden dabei ERSETZT, nicht weiterbenutzt: eine geaenderte
        Kacheltabelle laesst sich nicht in ein laufendes Display hineinreichen, ohne dass
        irgendwo ein alter Zustand haengenbleibt. Der Preis ist, dass Handauswahl und
        laufende Meldungen zuruecksetzen; dafuer gibt es keinen Zwischenzustand, der zur
        Haelfte alt ist.
        """
        try:
            neu = lade(self.pfad)
        except ConfigError as e:
            _LOG.error("Neu laden abgelehnt — %s", e)
            # Nur merken, wenn gerade ueberhaupt nichts laeuft: laeuft eine gueltige
            # Beschreibung weiter, waere „Beschreibung fehlerhaft" in der Oberflaeche
            # irrefuehrend — die Anzeige zeichnet ja.
            if not self.displays:
                self.ladefehler = str(e)
            return False

        await self._stoppe_displays()
        self.cfg = neu

        # ⚠ Schriften und Symbole MUESSEN mit neu aufgebaut werden. Beide lesen ihr
        # Verzeichnis nur beim Anlegen, und die Schriftregeln stehen in der Beschreibung
        # selbst. Ohne diese zwei Zeilen blieb eine neue PNG-Datei in `aton_icons`
        # unsichtbar und eine Aenderung an `fonts:` wirkungslos, bis jemand die ganze App
        # neu startete — und niemand haette geraten, dass ausgerechnet das noetig ist.
        self.fonts = FontRegistry(neu.fonts)
        self.icons = IconRegistry()

        self.displays = {p.id: Display(p, self.ha, self.fonts, self.icons)
                         for p in neu.panels}
        self.ladefehler = ""
        self.starte_displays()
        _LOG.info("Beschreibung neu geladen: %d Anzeige(n), %d Schriften, %d Symbole",
                  len(neu.panels), len(self.fonts.namen()), len(self.icons.namen()))
        return True


def optionen() -> dict:
    if os.path.exists(OPTIONS_PATH):
        with open(OPTIONS_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    return {}


def protokoll(stufe: str) -> None:
    stufen = {"trace": logging.DEBUG, "debug": logging.DEBUG, "info": logging.INFO,
              "warning": logging.WARNING, "error": logging.ERROR}
    logging.basicConfig(
        level=stufen.get(stufe, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )
    # aiohttps Zugriffsprotokoll waere hier nur Rauschen (die Oberflaeche pollt).
    logging.getLogger("aiohttp.access").setLevel(logging.WARNING)


async def main() -> int:
    opt = optionen()
    protokoll(str(opt.get("log_level", "info")))

    pfad = str(opt.get("config_file", "aton.yaml"))
    if not os.path.isabs(pfad):
        pfad = os.path.join(HA_CONFIG_DIR, pfad)

    # Nach aussen der Pfad, den der Benutzer im Editor sieht (/config/…) — im Container
    # heisst derselbe Ordner /homeassistant, und wer das liest, sucht die Datei vergeblich.
    sichtbar = anzeige_pfad(pfad)

    # ★★ Eine fehlerhafte Beschreibung darf die App NICHT beenden. Vorher tat sie genau
    # das (`return 1`) — mit der Folge, dass auch die OBERFLAECHE nie hochkam: reparieren
    # liess sich der Fehler dann nur noch ueber den Dateieditor oder die Konsole, also
    # ausgerechnet nicht dort, wo die Beschreibung sonst gepflegt wird. Dazu startete der
    # Supervisor die App in einer Schleife immer wieder neu.
    #
    # Jetzt: ohne Anzeigen starten, den Fehler festhalten, Oberflaeche hoch. Der
    # Konfigurator liest die Datei roh (nicht ueber diese Pruefung) — man kann sie also
    # bearbeiten und mit „Neu laden" wieder in Gang bringen, ohne die App anzufassen.
    ladefehler = ""
    try:
        cfg = lade(pfad)
    except ConfigError as e:
        ladefehler = str(e).replace(pfad, sichtbar)
        _LOG.error("Beschreibung fehlerhaft — %s", ladefehler)
        _LOG.error("Es wird nichts gezeichnet, bis das behoben ist. Die Oberflaeche "
                   "laeuft weiter: Datei %s im Konfigurator korrigieren und neu laden.",
                   sichtbar)
        cfg = AppCfg(quelle=pfad)

    # Sicherungen frueherer Fassungen lagen direkt in /config und haben den Dateibrowser
    # zugemuellt. Einmal beim Start einsammeln — danach schreibt `configfile.schreibe`
    # ohnehin in den Unterordner.
    configfile.sicherungen_umziehen(pfad)
    configfile.sicherungen_aufraeumen(pfad)

    if not ladefehler:
        _LOG.info("Beschreibung gelesen: %s (%d Anzeige(n))", sichtbar, len(cfg.panels))
    for p in cfg.panels:
        _LOG.info("  · %s: %dx%d @ %s, %d Widget(s), %d Screen-Gruppe(n), %d Entitaet(en)",
                  p.id, p.width, p.height, p.host, len(p.widgets), len(p.groups),
                  len(p.entities))

    fonts, icons = FontRegistry(cfg.fonts), IconRegistry()
    katalog = Katalog()
    ha = HomeAssistant()
    loop = asyncio.get_running_loop()

    # Sich bei Home Assistant anmelden, damit die Begleit-Integration von selbst
    # gefunden wird. Scheitert das, laesst sie sich weiterhin von Hand einrichten.
    anmeldung = Anmeldung(INGRESS_PORT)
    await anmeldung.anmelden()

    zustand = AppState(cfg, pfad, ha, fonts, icons, katalog)
    zustand.ladefehler = ladefehler
    zustand.displays = {p.id: Display(p, ha, fonts, icons) for p in cfg.panels}

    runner = await web.starte(zustand)
    ende = asyncio.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, ende.set)

    async with aiohttp.ClientSession() as session:
        zustand.session = session
        ha_aufgabe = asyncio.create_task(ha.run(), name="hass")
        zustand.starte_displays()
        await ende.wait()
        _LOG.info("Beende …")
        ha_aufgabe.cancel()
        await zustand._stoppe_displays()
        await asyncio.gather(ha_aufgabe, return_exceptions=True)

    await runner.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
