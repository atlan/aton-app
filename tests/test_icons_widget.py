"""Der Widget-Typ `icons`: eine Liste von Symbolen, aus einer Vorlage.

Die Fallen liegen nicht im Zeichnen, sondern in der Anordnung und im Umgang mit Unfug:

1. Symbole sind unterschiedlich breit. Wer sie aneinanderreiht, bekommt eine zweite Zeile,
   die nicht mehr unter der ersten steht — deshalb feste Zellen.
2. Eine Liste kommt aus einer Vorlage. Ein einzelner Tippfehler darin ist der NORMALFALL,
   nicht die Ausnahme: er darf die Kachel nicht kosten, muss aber auffallen.
3. Was nicht in die Fläche passt, muss abgeschnitten UND gemeldet werden. Stilles
   Weglassen sieht aus wie „die Vorlage liefert zu wenig".
"""
import textwrap

from panel.config import lade
from panel.fonts import FontRegistry
from panel.icons import IconRegistry
from panel.render import Renderer


def beschreibung(tmp_path, widgets, groesse="[64, 32]", name="aton.yaml"):
    kopf = ("panels:\n  - id: t\n    name: T\n    host: 1.2.3.4\n"
            f"    size: {groesse}\n    widgets:\n")
    pfad = tmp_path / name
    pfad.write_text(kopf + textwrap.indent(textwrap.dedent(widgets).strip("\n"), " " * 6),
                    encoding="utf-8")
    return lade(str(pfad)).panels[0]


class Quelle:
    def __init__(self, **z):
        self.z = z

    def state(self, eid):
        return self.z.get(eid)

    def attr(self, eid, name):
        return None


def zeichne(panel, quelle=None):
    return Renderer(panel, quelle or Quelle(), FontRegistry(), IconRegistry()).frame()


def belegte_spalten(bild, y0, y1):
    """Welche x-Spalten im Streifen y0..y1 etwas zeigen — daran sieht man die Anordnung."""
    return [x for x in range(bild.width)
            if any(bild.getpixel((x, y)) != (0, 0, 0) for y in range(y0, y1))]


# ==========================================================================
#  Quelle der Liste
# ==========================================================================
def test_liste_aus_vorlage(tmp_path):
    panel = beschreibung(tmp_path, """
        - type: icons
          at: [0, 0]
          size: [64, 8]
          template: "info, alert, bell"
    """)
    ergebnis = zeichne(panel)
    assert ergebnis.fehler == []
    assert ergebnis.bild.getbbox() is not None      # es steht etwas da


def test_trennung_per_komma_und_leerzeichen(tmp_path):
    """Beides muss gehen — eine Jinja-Schleife liefert mal das eine, mal das andere."""
    a = beschreibung(tmp_path, """
        - type: icons
          at: [0, 0]
          size: [64, 8]
          template: "info,alert,bell"
    """, name="a.yaml")
    b = beschreibung(tmp_path, """
        - type: icons
          at: [0, 0]
          size: [64, 8]
          template: "info alert  bell"
    """, name="b.yaml")
    assert list(zeichne(a).bild.getdata()) == list(zeichne(b).bild.getdata())


def test_ohne_textquelle_wird_abgelehnt(tmp_path):
    """Ein `icons` ohne Quelle kann nichts anzeigen — das gehoert beim Laden gesagt."""
    import pytest

    from panel.config import ConfigError
    with pytest.raises(ConfigError) as e:
        beschreibung(tmp_path, """
            - type: icons
              at: [0, 0]
              size: [64, 8]
        """)
    assert "Textquelle" in str(e.value)


# ==========================================================================
#  Anordnung
# ==========================================================================
def test_umbruch_in_die_naechste_zeile(tmp_path):
    """Sechs Symbole in eine 24 px breite Flaeche: drei je Zeile, zwei Zeilen."""
    panel = beschreibung(tmp_path, """
        - type: icons
          at: [0, 0]
          size: [24, 20]
          spacing: 0
          template: "info info info info info info"
    """)
    bild = zeichne(panel).bild
    zeile1 = belegte_spalten(bild, 0, 8)
    zeile2 = belegte_spalten(bild, 8, 16)
    assert zeile1 and zeile2, "es muss zwei Zeilen geben"
    # ★ Der eigentliche Punkt: die zweite Zeile steht UNTER der ersten, nicht versetzt.
    assert zeile1 == zeile2


def test_gleichmaessige_zellen_bei_verschieden_breiten_symbolen(tmp_path):
    """`cal` ist 9 px breit, alle anderen 8 — die Spalten muessen trotzdem stimmen.

    Geprueft wird ueber zwei GLEICH belegte Zeilen: `cal info` / `cal info`. Sind die
    Zellen fest, sind beide Streifen pixelgleich; reiht man die Symbole dagegen einfach
    aneinander, schoebe das 9 px breite `cal` die zweite Zeile um ein Pixel.

    ⚠ Zwei Fehlversuche davor, beide meine Schuld: erst zwei Symbole fuer verschieden
    breit gehalten (die eingebauten sind bis auf `cal` alle 8x8), dann leuchtende Spalten
    verglichen — die haengen am Bitmap des Symbols, nicht an seiner Zelle.
    """
    reg = IconRegistry()
    assert reg.get("cal").width != reg.get("info").width, "Voraussetzung des Tests"
    zelle = max(reg.get("cal").width, reg.get("info").width)      # = 9

    panel = beschreibung(tmp_path, f"""
        - type: icons
          at: [0, 0]
          size: [{2 * zelle}, 20]
          spacing: 0
          template: "cal info cal info"
    """)
    bild = zeichne(panel).bild
    oben  = bild.crop((0, 0, bild.width, 8)).tobytes()
    unten = bild.crop((0, 8, bild.width, 16)).tobytes()
    assert oben == unten, "zweite Zeile steht nicht deckungsgleich unter der ersten"
    assert bild.crop((0, 0, bild.width, 8)).getbbox() is not None


def test_ausrichtung_rechts(tmp_path):
    links = beschreibung(tmp_path, """
        - type: icons
          at: [0, 0]
          size: [64, 8]
          template: "info info"
    """, name="l.yaml")
    rechts = beschreibung(tmp_path, """
        - type: icons
          at: [0, 0]
          size: [64, 8]
          align: right
          template: "info info"
    """, name="r.yaml")
    sl = belegte_spalten(zeichne(links).bild, 0, 8)
    sr = belegte_spalten(zeichne(rechts).bild, 0, 8)
    assert min(sl) < min(sr) and max(sr) > max(sl)


# ==========================================================================
#  Unfug in der Liste
# ==========================================================================
def test_unbekanntes_symbol_kostet_nicht_die_kachel(tmp_path):
    """Ein Tippfehler in EINEM Namen — die uebrigen muessen trotzdem stehen."""
    panel = beschreibung(tmp_path, """
        - type: icons
          at: [0, 0]
          size: [64, 8]
          template: "info, gibtesnicht, bell"
    """)
    ergebnis = zeichne(panel)
    assert ergebnis.bild.getbbox() is not None          # gezeichnet wurde trotzdem
    assert any("gibtesnicht" in f for f in ergebnis.fehler)


def test_zu_viele_symbole_werden_gemeldet(tmp_path):
    """Abschneiden ja — aber nicht stillschweigend."""
    panel = beschreibung(tmp_path, """
        - type: icons
          at: [0, 0]
          size: [16, 8]
          spacing: 0
          template: "info info info info info info"
    """)
    ergebnis = zeichne(panel)
    assert any("abgeschnitten" in f for f in ergebnis.fehler)


def test_leere_liste_zeichnet_nichts(tmp_path):
    """Eine Vorlage, die (noch) nichts liefert, ist kein Fehler."""
    panel = beschreibung(tmp_path, """
        - type: icons
          at: [0, 0]
          size: [64, 8]
          template: "{{ '' }}"
    """)
    ergebnis = zeichne(panel)
    assert ergebnis.bild.getbbox() is None
    assert ergebnis.fehler == []
