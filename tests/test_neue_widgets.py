"""Die drei Typen aus 0.21.0: `bar`, `lines`, `sparkline`.

Geprueft wird, was still schiefgehen kann — nicht, dass Pillow Rechtecke malen kann:

* ein **fehlender Wert** darf keinen Balken bei 0 % ergeben. `unknown` heisst „ich weiss
  es nicht", nicht „leer", und ein Balken auf null waere eine Aussage, die der Sensor nie
  gemacht hat.
* eine **Kurve ohne Daten** darf keine Linie auf der Grundlinie zeichnen — die saehe aus
  wie „der Wert war die ganze Zeit null".
* eine **Kurve ohne feste Skala** muss die Spanne der Daten nehmen. Mit einer festen 0
  waere eine Aussentemperatur um 20 °C eine waagerechte Linie ganz oben.
* `lines` muss **kuerzen statt umbrechen** und sagen, was weggefallen ist.
"""
import types

from PIL import Image

from panel.config import TextSpec, Widget
from panel.render import Renderer
from panel.verlauf import _verdichten


class QuelleAttrappe:
    def __init__(self, werte=None):
        self.werte = werte or {}

    def state(self, eid):
        return self.werte.get(eid)

    def attr(self, eid, name):
        return None


class SchriftAttrappe:
    def measure(self, text):
        return (len(text) * 4, 6)

    def draw(self, d, xy, text, rgb):
        pass


class SchriftenAttrappe:
    def get(self, name=None):
        return SchriftAttrappe()


class SymboleAttrappe:
    def get(self, name):
        if name == "ok":
            return Image.new("RGBA", (8, 8), (255, 0, 0, 255))
        raise KeyError(name)


class VerlaufAttrappe:
    def __init__(self, punkte=None, grund=""):
        self._punkte = punkte or []
        self._grund = grund

    def punkte(self, eid, stunden):
        return self._punkte

    def fehler(self, eid, stunden):
        return self._grund


def renderer(werte=None, verlauf=None):
    panel = types.SimpleNamespace(
        id="p", width=64, height=32,
        grid=types.SimpleNamespace(row_height=9, col_width=32, icon_width=8, gap=1))
    r = Renderer.__new__(Renderer)
    r.panel = panel
    r.quelle = QuelleAttrappe(werte)
    r.fonts = SchriftenAttrappe()
    r.icons = SymboleAttrappe()
    r.verlauf = verlauf
    r.tmpl = types.SimpleNamespace(render=lambda t: t)
    r._gemeldet = set()
    return r


def leer():
    return Image.new("RGB", (64, 32), (0, 0, 0))


def bunt(bild):
    return sum(1 for p in bild.getdata() if p != (0, 0, 0))


# ── bar ─────────────────────────────────────────────────────────────────────

def test_balken_fuellt_anteilig():
    r = renderer({"sensor.x": "50"})
    w = Widget(type="bar", x=0, y=0, w=40, h=4, color="ffffff",
               text=TextSpec(entity="sensor.x"), skala_min=0.0, skala_max=100.0)
    b = leer()
    r._balken(b, w)
    assert bunt(b) == 20 * 4, "50 % von 40 px sind 20 Spalten"


def test_balken_ohne_wert_bleibt_leer():
    """Der Kern: `unavailable` darf nicht als 0 % durchgehen."""
    r = renderer({"sensor.x": "unavailable"})
    w = Widget(type="bar", x=0, y=0, w=40, h=4, color="ffffff",
               text=TextSpec(entity="sensor.x"))
    b, fehler = leer(), []
    r._balken(b, w, fehler)
    assert bunt(b) == 0
    assert fehler and "kein Zahlenwert" in fehler[0]


def test_balken_begrenzt_statt_ueberzulaufen():
    r = renderer({"sensor.x": "300"})
    w = Widget(type="bar", x=0, y=0, w=40, h=4, color="ffffff",
               text=TextSpec(entity="sensor.x"), skala_min=0.0, skala_max=100.0)
    b = leer()
    r._balken(b, w)
    assert bunt(b) == 40 * 4, "ueber 100 % bleibt voll, nicht breiter als die Kachel"


def test_balken_senkrecht_fuellt_von_unten():
    r = renderer({"sensor.x": "25"})
    w = Widget(type="bar", x=0, y=0, w=4, h=32, color="ffffff", vertical=True,
               text=TextSpec(entity="sensor.x"), skala_min=0.0, skala_max=100.0)
    b = leer()
    r._balken(b, w)
    assert b.getpixel((0, 31)) != (0, 0, 0), "unten gefuellt"
    assert b.getpixel((0, 0)) == (0, 0, 0), "oben frei"


# ── lines ───────────────────────────────────────────────────────────────────

def test_zeilen_meldet_was_nicht_passt():
    r = renderer()
    w = Widget(type="lines", x=0, y=0, w=64, h=8, color="ffffff",
               text=TextSpec(literal="eins\nzwei\ndrei\nvier"), spacing=1)
    fehler = []
    r._zeilen(leer(), w, fehler)
    assert fehler and "weggelassen" in fehler[0], "stilles Weglassen sieht aus wie zu wenig Daten"


def test_zeilen_kuerzt_statt_umzubrechen():
    r = renderer()
    font = SchriftAttrappe()
    assert r._kuerzen("abcdefghij", font, 20) == "abcde", "20 px / 4 px je Zeichen"
    assert r._kuerzen("kurz", font, 100) == "kurz", "was passt, bleibt ganz"


def test_zeilen_symbol_am_zeilenanfang():
    r = renderer()
    w = Widget(type="lines", x=0, y=0, w=64, h=32, color="ffffff",
               text=TextSpec(literal="@ok fertig"))
    b = leer()
    r._zeilen(b, w)
    assert b.getpixel((0, 0)) == (255, 0, 0), "das Symbol steht vorn"


def test_zeilen_unbekanntes_symbol_kostet_nur_die_zeile():
    r = renderer()
    w = Widget(type="lines", x=0, y=0, w=64, h=32, color="ffffff",
               text=TextSpec(literal="@gibtsnicht text"))
    fehler = []
    r._zeilen(leer(), w, fehler)
    assert fehler and "gibtsnicht" in fehler[0]


# ── sparkline ───────────────────────────────────────────────────────────────

def test_kurve_ohne_daten_zeichnet_nichts():
    r = renderer(verlauf=VerlaufAttrappe([], "noch nicht geholt"))
    w = Widget(type="sparkline", x=0, y=0, w=64, h=16, color="ffffff",
               text=TextSpec(entity="sensor.t"))
    b, fehler = leer(), []
    r._kurve(b, w, fehler)
    assert bunt(b) == 0, "eine Linie auf der Grundlinie waere eine erfundene Aussage"
    assert fehler and "kein Verlauf" in fehler[0]


def test_kurve_ohne_skala_nimmt_die_spanne_der_daten():
    """Bei 20,0 bis 20,4 °C muss die Kurve die Hoehe ausnutzen, nicht flach oben liegen."""
    r = renderer(verlauf=VerlaufAttrappe([20.0, 20.2, 20.4]))
    w = Widget(type="sparkline", x=0, y=0, w=8, h=16, color="ffffff",
               text=TextSpec(entity="sensor.t"))
    b = leer()
    r._kurve(b, w)
    hoehen = [y for x in range(8) for y in range(16) if b.getpixel((x, y)) != (0, 0, 0)]
    assert max(hoehen) - min(hoehen) > 10, "die Spanne wird auf die volle Hoehe gelegt"


def test_kurve_konstanter_wert_teilt_nicht_durch_null():
    r = renderer(verlauf=VerlaufAttrappe([7.0, 7.0, 7.0, 7.0]))
    w = Widget(type="sparkline", x=0, y=0, w=8, h=16, color="ffffff",
               text=TextSpec(entity="sensor.t"))
    b = leer()
    r._kurve(b, w)          # darf nicht werfen
    assert bunt(b) > 0


# ── Verdichten ──────────────────────────────────────────────────────────────

def test_verdichten_mittelt_statt_wegzuwerfen():
    """Jeden n-ten Wert zu nehmen wuerde genau die Spitze verlieren, die man sehen will."""
    werte = [0.0] * 9 + [90.0]          # eine Spitze ganz am Ende
    heraus = _verdichten(werte, 5)
    assert len(heraus) == 5
    assert heraus[-1] > 0, "die Spitze ueberlebt das Eindampfen"
    assert sum(heraus[:-1]) == 0


def test_verdichten_laesst_kurze_reihen_in_ruhe():
    assert _verdichten([1.0, 2.0], 10) == [1.0, 2.0]
