"""Konstanten der Matrix-Panel-Integration."""
from __future__ import annotations

DOMAIN = "aton"

CONF_HOST = "host"
CONF_PORT = "port"

# Vorgabe fuer die Handeingabe: so heisst die App im internen Netz, wenn sie als
# lokale App installiert ist. Der Supervisor ersetzt dabei Unterstriche durch
# Bindestriche ({REPO}_{SLUG} -> Hostname).
DEFAULT_HOST = "local-matrix-panel"
DEFAULT_PORT = 8099

# Der Takt der App liegt bei 5 s; oefter abzufragen bringt nichts.
UPDATE_INTERVAL = 5

AUTOMATIK = "Automatik"

SERVICE_NOTIFY = "notify"
SERVICE_NOTIFY_CLEAR = "notify_clear"

ATTR_PANEL = "panel"
ATTR_TEXT = "text"
ATTR_LEVEL = "level"
ATTR_DURATION = "duration"
ATTR_ID = "id"
ATTR_PRIORITY = "priority"
