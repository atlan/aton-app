"""Feste Pfade und Vorgaben der App."""
from __future__ import annotations

import os

# --- Add-on-Umgebung -------------------------------------------------------
OPTIONS_PATH = "/data/options.json"
DATA_DIR = "/data"
HA_CONFIG_DIR = "/homeassistant"          # map: homeassistant_config
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
SUPERVISOR_URL = "http://supervisor"
HA_WS_URL = "ws://supervisor/core/websocket"

# Ausserhalb des Add-ons (lokaler Test) ueberschreibbar
if os.environ.get("ATON_DEV"):
    HA_CONFIG_DIR = os.environ.get("ATON_CONFIG_DIR", os.getcwd())
    HA_WS_URL = os.environ.get("ATON_WS_URL", "ws://localhost:8123/api/websocket")

# --- Mitgelieferte Betriebsmittel -----------------------------------------
APP_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_DIR = os.path.join(APP_DIR, "fonts")            # zur Bauzeit erzeugt
WWW_DIR = os.path.join(APP_DIR, "www")

# --- Vom Benutzer befuellbar ----------------------------------------------
USER_FONT_DIR = os.path.join(HA_CONFIG_DIR, "aton_fonts")
USER_ICON_DIR = os.path.join(HA_CONFIG_DIR, "aton_icons")


def anzeige_pfad(pfad: str) -> str:
    """Pfad so schreiben, wie der Benutzer ihn kennt.

    Im Container heisst der HA-Konfigurationsordner `/homeassistant` (so blendet ihn
    `map: homeassistant_config` ein). Im Studio Code Server, im File Editor und ueber
    Samba heisst genau derselbe Ordner `/config`. Es ist EINE Datei — aber wer den
    Container-Pfad liest, sucht sie im Editor vergeblich. Nach aussen also `/config`.
    """
    if pfad.startswith(HA_CONFIG_DIR + "/"):
        return "/config/" + pfad[len(HA_CONFIG_DIR) + 1:]
    return pfad


def version() -> str:
    """Version der App aus `config.yaml`, oder `"?"` wenn sie nicht lesbar ist.

    ⚠ Die EINZIGE Quelle. In `panel/__init__.py` stand frueher ein zweites
    `__version__ = "0.1.0"`, das niemand mitzog — nur die `config.yaml` liest auch
    der Supervisor, alles andere laeuft irgendwann auseinander.

    Von Hand geparst statt ueber einen YAML-Leser: die Funktion wird auch dort
    gerufen, wo noch nichts geladen ist.
    """
    try:
        with open(os.path.join(APP_DIR, "config.yaml"), encoding="utf-8") as fh:
            for zeile in fh:
                if zeile.startswith("version:"):
                    return zeile.split(":", 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return "?"


# --- Netz ------------------------------------------------------------------
INGRESS_PORT = 8099

# --- Vorgaben --------------------------------------------------------------
DEFAULT_FONT = "5x3"
DEFAULT_COLOR = "ffffff"
DEFAULT_INTERVAL = 5.0
UNAVAILABLE_STATES = (None, "", "unknown", "unavailable", "None")

# Stellung "Automatik" einer Screen-Gruppe (keine Handauswahl)
AUTOMATIK = "Automatik"
