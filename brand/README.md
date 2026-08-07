# Logo für die Integrationskachel

Home Assistant holt das Logo einer Integration aus dem Repository
[home-assistant/brands](https://github.com/home-assistant/brands). Custom-Integrationen
haben dort einen eigenen Ordner: `custom_integrations/<domain>/`, erwartet werden genau
zwei Dateien — geprüft an einem vorhandenen Eintrag (`custom_integrations/hacs/`):

| Datei | Größe |
|---|---|
| `icon.png` | 256×256 |
| `icon@2x.png` | 512×512 |

Die beiden Dateien hier sind fertig. Für die Kachel in **Einstellungen → Geräte & Dienste**
müssen sie per Pull Request nach `custom_integrations/aton/` in jenes Repository —
lokal lässt sich das Logo nicht hinterlegen.

Ohne den PR zeigt HA den allgemeinen Platzhalter für Custom-Integrationen. Die Icons der
Entitäten und Dienste sind davon **nicht** betroffen: die kommen aus `icons.json` und sind
sofort da.

Erzeugt mit Pillow; das Motiv ist ein Ausschnitt einer LED-Matrix mit zwei Kacheln aus
Symbol und Wert — so, wie die Anzeige aus dem Raum aussieht.
