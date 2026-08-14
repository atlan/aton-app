"""Beispiel fuer einen eigenen Widget-Typ: ein Balken als Fuellstandsanzeige.

Kopieren nach `/config/aton_widgets/bargraph.py` und in der App-Konfiguration
`custom_widgets: true` setzen. Danach in der YAML:

    - type: bargraph
      at: [0, 0]
      size: [32, 3]
      sensor: sensor.zisterne_fuellstand
      max: 100
      bar_color: 3080ff
      track_color: 202020
"""
from aton_api import Feld, widget


@widget(
    "bargraph",
    beschreibung="Waagerechter Balken — fuellt sich zwischen 'min' und 'max'",
    felder=[
        # ⚠ NICHT `value` nennen: der Schluessel gehoert zur eingebauten Textquelle und
        # kaeme nie beim Plugin an. Der Loader lehnt so ein Feld deshalb schon beim Laden
        # ab, statt es still zu verschlucken.
        Feld("sensor", "entitaet", "Sensor", "Zustand, der den Fuellstand bestimmt",
             pflicht=True),
        Feld("min", "float", "Anfang", vorgabe=0.0),
        Feld("max", "float", "Vollausschlag", vorgabe=100.0),
        Feld("bar_color", "farbe", "Balkenfarbe", vorgabe="30c030"),
        Feld("track_color", "farbe", "Spurfarbe",
             "Der ungefuellte Teil. Leer lassen = gar nicht zeichnen"),
    ],
)
def zeichne(bild, w, ctx):
    o = w.optionen
    d = ctx.zeichner(bild)

    if o.get("track_color"):
        d.rectangle([w.x, w.y, w.x + w.w - 1, w.y + w.h - 1], fill=ctx.rgb(o["track_color"]))

    wert = ctx.zahl(o["sensor"])
    if wert is None:
        # unknown / unavailable / kein Zahlenwert: leere Spur stehen lassen. Ein Balken bei
        # 0 % waere hier eine Aussage, die der Sensor gar nicht gemacht hat.
        return

    spanne = o["max"] - o["min"]
    if spanne <= 0:
        return
    anteil = min(1.0, max(0.0, (wert - o["min"]) / spanne))
    breite = round(w.w * anteil)
    if breite:
        d.rectangle([w.x, w.y, w.x + breite - 1, w.y + w.h - 1], fill=ctx.rgb(o["bar_color"]))
