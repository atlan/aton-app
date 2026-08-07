#!/usr/bin/with-contenv bash
# ⚠ Das `with-contenv` in der Shebang-Zeile ist PFLICHT, keine Verzierung.
#
# s6 startet Dienste mit einer LEEREN Umgebung. Ohne diesen Wrapper bekommt die App
# genau eine Variable (PATH) — und damit kein SUPERVISOR_TOKEN. Die Folge sieht nicht
# nach einem Umgebungsproblem aus, sondern nach kaputten Zugangsdaten:
#   · MQTT:      401 Unauthorized von http://supervisor/services/mqtt
#   · HA-Socket: {"type": "auth_invalid", "message": "Invalid access"}
#
# ⚠ Und `docker exec ... env` zeigt das NICHT — dort erscheint die Container-Umgebung,
# nicht die des Dienstes. Nachsehen im laufenden Prozess:
#   tr '\0' '\n' < /proc/$(docker inspect -f '{{.State.Pid}}' app_local_aton)/environ
set -e
exec python3 -m panel
