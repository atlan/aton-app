"""User-supplied widget types from /config/aton_widgets.

This is the one feature where the app runs code it did not ship. Three things must hold,
and each of them is silent when broken:

1. The switch. With `custom_widgets` off, the directory is not read at all — not "read but
   ignored". A test that only checks the rendered image cannot tell those apart.
2. The declared fields really gate the YAML. The whole point of declaring them was to get
   a typo reported instead of swallowed; if validation quietly passes everything, the
   feature still *looks* like it works.
3. A broken plugin costs its own tile and nothing else. Import errors, a field name that
   collides with a built-in key, an exception while drawing — none of them may take down
   the frame, and each must name the file it came from.
"""
import textwrap

import pytest
from PIL import Image

from panel import plugin
from panel.config import ConfigError, lade
from panel.fonts import FontRegistry
from panel.icons import IconRegistry
from panel.render import Renderer


BARGRAPH = """
    from aton_api import Feld, widget

    @widget("bargraph", beschreibung="Balken", felder=[
        Feld("sensor", "entitaet", "Sensor", pflicht=True),
        Feld("max", "float", "Vollausschlag", vorgabe=100.0, min=1, max=1000),
        Feld("bar_color", "farbe", "Balkenfarbe", vorgabe="30c030"),
    ])
    def zeichne(bild, w, ctx):
        wert = ctx.zahl(w.optionen["sensor"]) or 0
        anteil = min(1.0, max(0.0, wert / w.optionen["max"]))
        breite = round(w.w * anteil)
        if breite:
            ctx.zeichner(bild).rectangle(
                [w.x, w.y, w.x + breite - 1, w.y + w.h - 1],
                fill=ctx.rgb(w.optionen["bar_color"]))
"""


@pytest.fixture
def widget_dir(tmp_path):
    """A plugin directory plus a helper to fill it. Always resets the global registry."""
    verzeichnis = tmp_path / "aton_widgets"
    verzeichnis.mkdir()

    def schreibe(name, quelle):
        (verzeichnis / f"{name}.py").write_text(textwrap.dedent(quelle), encoding="utf-8")

    def lade_registry(aktiv=True):
        plugin.registry.lade(aktiv, str(verzeichnis))
        return plugin.registry

    yield schreibe, lade_registry
    plugin.registry.lade(False, str(verzeichnis))


def beschreibung(tmp_path, widgets, groesse="[32, 16]"):
    kopf = ("panels:\n"
            "  - id: t\n"
            "    name: T\n"
            "    host: 192.168.1.51\n"
            f"    size: {groesse}\n"
            "    dry_run: true\n"
            "    widgets:\n")
    pfad = tmp_path / "aton.yaml"
    pfad.write_text(kopf + textwrap.indent(textwrap.dedent(widgets).strip("\n"), " " * 6),
                    encoding="utf-8")
    return str(pfad)


class Quelle:
    def __init__(self, **zustaende):
        self.zustaende = zustaende

    def state(self, eid):
        return self.zustaende.get(eid)

    def attr(self, eid, name):
        return None


def zeichne(panel, quelle):
    return Renderer(panel, quelle, FontRegistry(), IconRegistry()).frame()


# ==========================================================================
#  Der Schalter
# ==========================================================================
def test_schalter_aus_liest_das_verzeichnis_nicht(widget_dir, tmp_path):
    schreibe, lade_registry = widget_dir
    schreibe("bargraph", BARGRAPH)
    reg = lade_registry(aktiv=False)

    assert reg.namen() == []
    # Nicht nur "keine Typen", sondern auch keine Fehler: die Datei wurde nicht angefasst.
    assert reg.fehler == []

    with pytest.raises(ConfigError) as e:
        lade(beschreibung(tmp_path, """
            - type: bargraph
              at: [0, 0]
              size: [32, 8]
              sensor: sensor.x
        """))
    # Die Meldung muss den Weg nach vorn zeigen, sonst sucht man im YAML statt in der
    # App-Konfiguration.
    assert "custom_widgets" in str(e.value)


def test_typ_steht_im_auswahlfeld_des_formulars(widget_dir):
    """★★ Die Oberfläche baut das Typ-Klappfeld aus `optionen` des FELDES `type`.

    `widget_typen` daneben zu ergänzen reicht nicht — dann steht der eigene Typ im Schema
    und ist im Konfigurator trotzdem nicht auswählbar. Von außen sieht das nach einem
    Zwischenspeicher aus, und man sucht tagelang an der falschen Stelle.
    """
    from panel import schema

    schreibe, lade_registry = widget_dir
    schreibe("bargraph", BARGRAPH)
    reg = lade_registry()

    d = schema.als_dict(None, "de", reg.als_dict(), reg.fehler)
    typ_feld = next(f for f in d["widget"] if f["name"] == "type")

    assert "bargraph" in typ_feld["optionen"], "eigener Typ fehlt im Klappfeld"
    assert "bargraph" in d["widget_typen"]
    assert typ_feld["optionen"] == d["widget_typen"]

    # ⚠ Und die eingebaute Liste darf dabei nicht mitwachsen: sie ist ein Modul-Objekt,
    # ein `append` darauf wuerde sich ueber alle folgenden Aufrufe hinweg aufsummieren.
    assert "bargraph" not in schema.WIDGET_TYPEN


def test_schalter_an_laedt_den_typ(widget_dir):
    schreibe, lade_registry = widget_dir
    schreibe("bargraph", BARGRAPH)
    reg = lade_registry()

    assert reg.namen() == ["bargraph"]
    assert reg.fehler == []
    assert reg.get("bargraph").beschreibung == "Balken"


# ==========================================================================
#  Die Felder gelten wirklich
# ==========================================================================
def test_eigene_schluessel_erlaubt_fremde_nicht(widget_dir, tmp_path):
    schreibe, lade_registry = widget_dir
    schreibe("bargraph", BARGRAPH)
    lade_registry()

    cfg = lade(beschreibung(tmp_path, """
        - type: bargraph
          at: [0, 0]
          size: [32, 8]
          sensor: sensor.x
          max: 50
    """))
    w = cfg.panels[0].widgets[0]
    assert w.optionen == {"sensor": "sensor.x", "max": 50.0, "bar_color": "30c030"}

    with pytest.raises(ConfigError) as e:
        lade(beschreibung(tmp_path, """
            - type: bargraph
              at: [0, 0]
              size: [32, 8]
              sensor: sensor.x
              maxx: 50
        """))
    assert "maxx" in str(e.value)


def test_uebriggebliebener_schluessel_nennt_seinen_typ(widget_dir, tmp_path):
    """★ Nach einem Typwechsel bleibt `sensor` stehen — das ist kein Tippfehler.

    Ohne den Hinweis liest man „unbekannter Schlüssel: sensor" und sucht einen Vertipper.
    Den Schlüssel hat aber nie jemand geschrieben; er stammt vom vorigen Typ.
    """
    schreibe, lade_registry = widget_dir
    schreibe("bargraph", BARGRAPH)
    lade_registry()

    with pytest.raises(ConfigError) as e:
        lade(beschreibung(tmp_path, """
            - type: clock
              at: [0, 0]
              size: [32, 8]
              sensor: sensor.x
        """))
    text = str(e.value)
    assert "sensor gehoert zu type: bargraph" in text
    assert "Wechsel des Typs" in text

    # Ein echter Tippfehler bleibt ein schlichter unbekannter Schluessel — der Zusatz
    # darf nicht bei allem erscheinen, sonst ist er Rauschen.
    with pytest.raises(ConfigError) as e2:
        lade(beschreibung(tmp_path, """
            - type: clock
              at: [0, 0]
              size: [32, 8]
              fnord: 1
        """))
    assert "gehoert zu type" not in str(e2.value)


def test_pflichtfeld_und_grenzen(widget_dir, tmp_path):
    schreibe, lade_registry = widget_dir
    schreibe("bargraph", BARGRAPH)
    lade_registry()

    with pytest.raises(ConfigError, match="sensor"):
        lade(beschreibung(tmp_path, """
            - type: bargraph
              at: [0, 0]
              size: [32, 8]
        """))

    with pytest.raises(ConfigError, match="groesser"):
        lade(beschreibung(tmp_path, """
            - type: bargraph
              at: [0, 0]
              size: [32, 8]
              sensor: sensor.x
              max: 5000
        """))


def test_entitaet_landet_in_den_abonnements(widget_dir, tmp_path):
    """★ Ohne das wird das Widget nie neu gezeichnet — und nichts sieht kaputt aus."""
    schreibe, lade_registry = widget_dir
    schreibe("bargraph", BARGRAPH)
    lade_registry()

    cfg = lade(beschreibung(tmp_path, """
        - type: bargraph
          at: [0, 0]
          size: [32, 8]
          sensor: sensor.zisterne
    """))
    assert "sensor.zisterne" in cfg.panels[0].entities


# ==========================================================================
#  Zeichnen
# ==========================================================================
def test_zeichnet_wirklich(widget_dir, tmp_path):
    schreibe, lade_registry = widget_dir
    schreibe("bargraph", BARGRAPH)
    lade_registry()

    cfg = lade(beschreibung(tmp_path, """
        - type: bargraph
          at: [0, 0]
          size: [32, 4]
          sensor: sensor.zisterne
          max: 100
          bar_color: ff0000
    """))
    erg = zeichne(cfg.panels[0], Quelle(**{"sensor.zisterne": "25"}))

    assert erg.fehler == []
    px = erg.bild.convert("RGB").load()
    gesetzt = [x for x in range(32) if px[x, 0] != (0, 0, 0)]
    assert gesetzt == list(range(8))               # 25 % von 32 px
    assert px[0, 0] == (255, 0, 0)


def test_unavailable_zeichnet_keinen_balken(widget_dir, tmp_path):
    schreibe, lade_registry = widget_dir
    schreibe("bargraph", BARGRAPH)
    lade_registry()

    cfg = lade(beschreibung(tmp_path, """
        - type: bargraph
          at: [0, 0]
          size: [32, 4]
          sensor: sensor.zisterne
    """))
    erg = zeichne(cfg.panels[0], Quelle(**{"sensor.zisterne": "unavailable"}))
    assert erg.fehler == []
    assert erg.bild.convert("RGB").getbbox() is None


# ==========================================================================
#  Kaputte Plugins
# ==========================================================================
def test_importfehler_nennt_die_datei_und_haelt_nichts_auf(widget_dir):
    schreibe, lade_registry = widget_dir
    schreibe("kaputt", "def (:")                   # echter Syntaxfehler
    schreibe("bargraph", BARGRAPH)
    reg = lade_registry()

    assert reg.namen() == ["bargraph"]             # das heile laedt weiter
    assert len(reg.fehler) == 1
    assert "kaputt.py" in reg.fehler[0]
    assert "SyntaxError" in reg.fehler[0]


def test_feldname_kollidiert_mit_eingebautem_schluessel(widget_dir):
    """`value` gehoert der eingebauten Textquelle — ein Plugin bekaeme es nie zu sehen."""
    schreibe, lade_registry = widget_dir
    schreibe("kollision", """
        from aton_api import Feld, widget

        @widget("kollision", felder=[Feld("value", "entitaet", "Sensor")])
        def zeichne(bild, w, ctx):
            pass
    """)
    reg = lade_registry()

    assert reg.namen() == []
    assert "value" in reg.fehler[0]
    assert "kollision.py" in reg.fehler[0]


def test_eingebauter_typname_wird_abgelehnt(widget_dir):
    schreibe, lade_registry = widget_dir
    schreibe("uhr", """
        from aton_api import widget

        @widget("clock")
        def zeichne(bild, w, ctx):
            pass
    """)
    reg = lade_registry()

    assert reg.namen() == []
    assert "eingebaut" in reg.fehler[0]


def test_datei_ohne_dekorator(widget_dir):
    schreibe, lade_registry = widget_dir
    schreibe("leer", "x = 1")
    reg = lade_registry()

    assert reg.namen() == []
    assert "@widget" in reg.fehler[0]


def test_ausnahme_beim_zeichnen_kostet_nur_die_kachel(widget_dir, tmp_path):
    schreibe, lade_registry = widget_dir
    schreibe("bombe", """
        from aton_api import widget

        @widget("bombe")
        def zeichne(bild, w, ctx):
            raise ZeroDivisionError("geplatzt")
    """)
    lade_registry()

    cfg = lade(beschreibung(tmp_path, """
        - type: bombe
          at: [0, 0]
          size: [8, 8]
        - type: text
          at: [0, 8]
          size: [32, 8]
          text: heil
    """))
    erg = zeichne(cfg.panels[0], Quelle())

    assert isinstance(erg.bild, Image.Image)       # ein Frame kam trotzdem heraus
    assert len(erg.fehler) == 1
    # Der Dateiname MUSS drinstehen: die Stelle in der YAML ist hier nicht das Problem.
    assert "bombe.py" in erg.fehler[0]
    assert "ZeroDivisionError" in erg.fehler[0]
    # Und das zweite Widget wurde trotzdem gezeichnet.
    assert erg.bild.convert("RGB").getbbox()[3] > 8


# ==========================================================================
#  Neu laden
# ==========================================================================
def test_neu_laden_sieht_geaenderte_dateien(widget_dir):
    schreibe, lade_registry = widget_dir
    schreibe("bargraph", BARGRAPH)
    assert lade_registry().namen() == ["bargraph"]

    schreibe("bargraph", BARGRAPH.replace('"bargraph"', '"balken"', 1))
    assert lade_registry().namen() == ["balken"]
