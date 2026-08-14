"""Der Widget-Typ `series`: Spalten aus Beschriftung, Symbol und Beschriftung.

Gebaut für die Stundenvorhersage (14|@sol_o|21, 15|@wet|20, …), aber nicht darauf
beschränkt. Der Grund für einen eigenen Typ statt dreier Kacheln steht im Renderer: die
Spalten sind hier bauartbedingt bündig, während `text`+`icons`+`text` daran hängt, dass
die Vorlage jede Beschriftung auf dieselbe Breite auffüllt.

Geprüft wird deshalb vor allem die Bündigkeit — und dass fehlende Teile keine Höhe kosten.
"""
import textwrap

from panel.config import lade
from panel.fonts import FontRegistry
from panel.icons import IconRegistry
from panel.render import Renderer


def beschreibung(tmp_path, widgets, groesse="[128, 64]", name="aton.yaml"):
    kopf = ("panels:\n  - id: t\n    name: T\n    host: 1.2.3.4\n"
            f"    size: {groesse}\n    widgets:\n")
    pfad = tmp_path / name
    pfad.write_text(kopf + textwrap.indent(textwrap.dedent(widgets).strip("\n"), " " * 6),
                    encoding="utf-8")
    return lade(str(pfad)).panels[0]


class Quelle:
    def state(self, eid):
        return None

    def attr(self, eid, name):
        return None


def zeichne(panel):
    return Renderer(panel, Quelle(), FontRegistry(), IconRegistry()).frame()


def spalten_mit_inhalt(bild, y0, y1):
    return [x for x in range(bild.width)
            if any(bild.getpixel((x, y)) != (0, 0, 0) for y in range(y0, y1))]


def test_drei_reihen_werden_gezeichnet(tmp_path):
    panel = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 22]
          spacing: 1
          template: "14|@sol_o|21, 15|@wet|20, 16|@dry|19"
    """)
    ergebnis = zeichne(panel)
    assert ergebnis.fehler == []
    bild = ergebnis.bild
    # oben Text, in der Mitte Symbole, unten Text — drei belegte Baender
    assert spalten_mit_inhalt(bild, 0, 5), "obere Beschriftung fehlt"
    assert spalten_mit_inhalt(bild, 6, 14), "Symbolreihe fehlt"
    assert spalten_mit_inhalt(bild, 15, 21), "untere Beschriftung fehlt"


def test_spalten_sind_buendig(tmp_path):
    """Der eigentliche Zweck des Typs.

    Zwei Spalten mit GLEICHEM Inhalt muessen pixelgleich sein — unabhaengig davon, dass
    ihre Nachbarn unterschiedlich breite Beschriftungen haben ('9' ist halb so breit wie
    '21'). Ohne feste Zellen verschoebe die schmale Spalte alles danach.
    """
    panel = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 22]
          spacing: 0
          template: "1|@sol_o|9, 14|@sol_o|21, 1|@sol_o|9"
    """)
    bild = zeichne(panel).bild
    reg = IconRegistry()
    zelle = max(reg.get("sol_o").width, FontRegistry().get("5x3").measure("21")[0])
    erste = bild.crop((0, 0, zelle, 22)).tobytes()
    dritte = bild.crop((2 * zelle, 0, 3 * zelle, 22)).tobytes()
    assert erste == dritte, "gleiche Spalten muessen deckungsgleich sein"


def test_abstaende_sind_symmetrisch(tmp_path):
    """Über und unter dem Symbol muss derselbe Abstand stehen — der aus `spacing`.

    ⚠ Genau das war falsch: `_schreibe` rückt seinen Text im Feld um 1 px nach unten,
    dadurch war die obere Lücke 1 px zu klein und die untere 1 px zu groß (gemessen bei
    spacing=2: 1 und 3 statt 2 und 2). Aufgefallen ist es am gerenderten Bild, nicht in
    den Tests — deshalb dieser hier.
    """
    for spacing in (0, 1, 2, 3):
        panel = beschreibung(tmp_path, f"""
            - type: series
              at: [0, 0]
              size: [128, 40]
              spacing: {spacing}
              template: "14|@sol_o|21, 15|@wet|20"
        """, groesse="[128, 40]", name=f"s{spacing}.yaml")
        bild = zeichne(panel).bild
        belegt = [y for y in range(40)
                  if any(bild.getpixel((x, y)) != (0, 0, 0) for x in range(bild.width))]
        baender, start = [], None
        for y in range(41):
            an = y in belegt
            if an and start is None:
                start = y
            if not an and start is not None:
                baender.append((start, y - 1))
                start = None
        luecken = [baender[i + 1][0] - baender[i][1] - 1 for i in range(len(baender) - 1)]
        if spacing == 0:
            assert luecken == [], f"spacing=0 muss buendig sein, ist {luecken}"
        else:
            assert luecken == [spacing, spacing], \
                f"spacing={spacing}: Luecken {luecken} statt [{spacing}, {spacing}]"


def test_zeilen_und_spaltenabstand_sind_getrennt(tmp_path):
    """`line_spacing` gilt senkrecht, `spacing` waagerecht — sonst ist eines immer falsch.

    Vom Benutzer am Bild bemerkt: Spalten brauchen Luft, die drei Reihen einer Spalte
    gehoeren dicht zusammen. Mit einem gemeinsamen Wert geht das nicht.
    """
    panel = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 40]
          spacing: 4
          line_spacing: 0
          template: "14|@sol_o|21, 15|@wet|20"
    """, groesse="[128, 40]")
    bild = zeichne(panel).bild

    # senkrecht: buendig, also EIN durchgehendes Band
    belegt = [y for y in range(40)
              if any(bild.getpixel((x, y)) != (0, 0, 0) for x in range(bild.width))]
    assert belegt == list(range(min(belegt), max(belegt) + 1)), \
        "line_spacing: 0 muss die Reihen buendig setzen"

    # waagerecht: zwischen den beiden Spalten muss eine Luecke von 4 px stehen
    spalten = [x for x in range(bild.width)
               if any(bild.getpixel((x, y)) != (0, 0, 0) for y in range(40))]
    luecken = [b - a - 1 for a, b in zip(spalten, spalten[1:]) if b - a > 1]
    assert 4 in luecken, f"waagerechte Luecken {luecken}, erwartet eine von 4 px"


def test_ohne_line_spacing_gilt_spacing(tmp_path):
    """Rueckwaertskompatibel: wer nur `spacing` setzt, bekommt es wie bisher auf beiden Achsen."""
    panel = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 40]
          spacing: 2
          template: "14|@sol_o|21, 15|@wet|20"
    """, groesse="[128, 40]", name="b.yaml")
    bild = zeichne(panel).bild
    belegt = [y for y in range(40)
              if any(bild.getpixel((x, y)) != (0, 0, 0) for x in range(bild.width))]
    baender, start = [], None
    for y in range(41):
        an = y in belegt
        if an and start is None:
            start = y
        if not an and start is not None:
            baender.append((start, y - 1))
            start = None
    luecken = [baender[i + 1][0] - baender[i][1] - 1 for i in range(len(baender) - 1)]
    assert luecken == [2, 2]


def test_fehlende_teile_kosten_keine_hoehe(tmp_path):
    """Nur Symbole: die Kachel darf nicht so hoch bauen, als gaebe es Beschriftungen."""
    nur_sym = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 22]
          spacing: 1
          template: "@sol_o, @wet, @dry"
    """, name="a.yaml")
    bild = zeichne(nur_sym).bild
    oben, unten = bild.getbbox()[1], bild.getbbox()[3]
    assert unten - oben <= 8, f"Symbolreihe belegt {unten - oben} px statt 8"


def test_umbruch_und_meldung(tmp_path):
    panel = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [20, 12]
          spacing: 0
          template: "1|@sol_o|1, 2|@sol_o|2, 3|@sol_o|3, 4|@sol_o|4, 5|@sol_o|5, 6|@sol_o|6"
    """)
    ergebnis = zeichne(panel)
    assert any("abgeschnitten" in f for f in ergebnis.fehler)


def test_unbekanntes_symbol_kostet_nicht_die_kachel(tmp_path):
    panel = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 22]
          template: "14|@gibtesnicht|21, 15|@sol_o|20"
    """)
    ergebnis = zeichne(panel)
    assert any("gibtesnicht" in f for f in ergebnis.fehler)
    # Die zweite Spalte samt Beschriftungen steht trotzdem.
    assert ergebnis.bild.getbbox() is not None


def test_ohne_textquelle_wird_abgelehnt(tmp_path):
    import pytest

    from panel.config import ConfigError
    with pytest.raises(ConfigError) as e:
        beschreibung(tmp_path, """
            - type: series
              at: [0, 0]
              size: [128, 22]
        """)
    assert "series" in str(e.value) and "Textquelle" in str(e.value)


def test_leere_vorlage_zeichnet_nichts(tmp_path):
    panel = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 22]
          template: "{{ '' }}"
    """)
    ergebnis = zeichne(panel)
    assert ergebnis.bild.getbbox() is None
    assert ergebnis.fehler == []


# ==========================================================================
#  Freie Anordnung — der Zweck von `@`
# ==========================================================================
def test_beliebige_anordnungen(tmp_path):
    """Nur Text, nur Symbole, Symbol über Text, ein einzelnes Symbol — alles eine Zeile."""
    faelle = {
        "zwei Textreihen":   ("Mo|Di, Mi|Do", 2 * 5 + 1),
        "zwei Symbolreihen": ("@sol_o|@wet, @dry|@wind", 2 * 8 + 1),
        "Symbol über Text":  ("@r_liv|22, @r_bat|21", 8 + 5 + 1),
        "nur ein Symbol":    ("@sol_o, @wet", 8),
    }
    for name, (vorlage, erwartet_h) in faelle.items():
        panel = beschreibung(tmp_path, f"""
            - type: series
              at: [0, 0]
              size: [128, 40]
              spacing: 2
              line_spacing: 1
              template: "{vorlage}"
        """, groesse="[128, 40]", name=f"{abs(hash(name))}.yaml")
        ergebnis = zeichne(panel)
        assert ergebnis.fehler == [], f"{name}: {ergebnis.fehler}"
        kasten = ergebnis.bild.getbbox()
        assert kasten is not None, f"{name}: nichts gezeichnet"
        hoehe = kasten[3] - kasten[1]
        assert hoehe <= erwartet_h, f"{name}: {hoehe} px hoch, erwartet höchstens {erwartet_h}"


def test_at_zeichen_trennt_symbol_von_text(tmp_path):
    """`info` ist Text, `@info` das Symbol — sonst könnte ein neu gezeichnetes Symbol
    bestehende Kacheln stillschweigend verändern."""
    als_text = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 20]
          template: "info"
    """, name="t.yaml")
    als_symbol = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 20]
          template: "@info"
    """, name="s.yaml")
    a, b = zeichne(als_text), zeichne(als_symbol)
    assert a.fehler == [] and b.fehler == []
    assert list(a.bild.getdata()) != list(b.bild.getdata()), \
        "Text und Symbol müssen verschieden aussehen"


def test_luecke_bei_unbekanntem_symbol_verschiebt_nichts(tmp_path):
    """Ein fehlendes Symbol darf die Reihen der NACHBARSPALTEN nicht verrutschen lassen."""
    panel = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 20]
          spacing: 0
          line_spacing: 0
          template: "1|@gibtesnicht|3, 1|@sol_o|3"
    """)
    ergebnis = zeichne(panel)
    assert any("gibtesnicht" in f for f in ergebnis.fehler)
    bild = ergebnis.bild
    # In beiden Spalten muss die untere Beschriftung auf derselben Höhe stehen.
    def zeilen(x0, x1):
        return [y for y in range(20)
                if any(bild.getpixel((x, y)) != (0, 0, 0) for x in range(x0, x1))]
    reg = IconRegistry()
    zelle = max(reg.get("sol_o").width, FontRegistry().get("5x3").measure("1")[0])
    assert max(zeilen(0, zelle)) == max(zeilen(zelle, 2 * zelle))


# ==========================================================================
#  Alte Namen bleiben gültig
# ==========================================================================
def test_alter_typname_serie_wird_angenommen(tmp_path):
    """Eine bestehende Beschreibung mit `type: serie` darf nicht scheitern."""
    alt = beschreibung(tmp_path, """
        - type: serie
          at: [0, 0]
          size: [128, 20]
          template: "14|@sol_o|21"
    """, name="alt.yaml")
    neu = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 20]
          template: "14|@sol_o|21"
    """, name="neu.yaml")
    assert alt.widgets[0].type == "series"
    assert list(zeichne(alt).bild.getdata()) == list(zeichne(neu).bild.getdata())


def test_alte_screen_schluessel_bleiben_gueltig(tmp_path):
    """`seiten`/`zyklen`/`wechsel_zyklen` heißen jetzt `pages`/`cycles`/`page_cycles`."""
    import textwrap

    from panel.config import lade
    rumpf = """
    panels:
      - id: t
        name: T
        host: 1.2.3.4
        size: [64, 32]
        screen_groups:
          - id: g
            region: [0, 0, 64, 32]
            screens:
              - name: s
                {wechsel}: 2
                {seiten}:
                  - name: eins
                    {zyklen}: 3
                    widgets: []
                  - name: zwei
                    widgets: []
    """
    ergebnisse = []
    for wechsel, seiten, zyklen, datei in (
            ("wechsel_zyklen", "seiten", "zyklen", "de.yaml"),
            ("page_cycles", "pages", "cycles", "en.yaml")):
        pfad = tmp_path / datei
        pfad.write_text(textwrap.dedent(
            rumpf.format(wechsel=wechsel, seiten=seiten, zyklen=zyklen)).strip(),
            encoding="utf-8")
        p = lade(str(pfad)).panels[0]
        sc = p.groups[0].screens[0]
        ergebnisse.append((sc.wechsel_zyklen, [se.zyklen for se in sc.seiten]))
    assert ergebnisse[0] == ergebnisse[1] == (2, [3, 0])


# ==========================================================================
#  Stil je Reihe
# ==========================================================================
def farben_im_streifen(bild, y0, y1):
    """Welche Farben kommen im Band y0..y1 vor (ohne Schwarz)?"""
    return {bild.getpixel((x, y)) for x in range(bild.width) for y in range(y0, y1)
            if bild.getpixel((x, y)) != (0, 0, 0)}


def test_farbe_je_reihe(tmp_path):
    """Erste Reihe gelb, dritte grün, mittlere unverändert."""
    panel = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 24]
          spacing: 2
          line_spacing: 1
          color: ffffff
          row_colors: [ffff00, "", 30c030]
          template: "14|@sol_o|21, 15|@sol_o|20"
    """, groesse="[128, 24]")
    ergebnis = zeichne(panel)
    assert ergebnis.fehler == []
    bild = ergebnis.bild
    assert (255, 255, 0) in farben_im_streifen(bild, 0, 5), "Reihe 1 nicht gelb"
    assert (48, 192, 48) in farben_im_streifen(bild, 14, 20), "Reihe 3 nicht grün"


def test_kommaliste_und_yaml_liste_sind_gleichwertig(tmp_path):
    """Im Formular tippt man eine Kommaliste, in der YAML schreibt man eine Liste."""
    a = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 24]
          row_colors: [ffff00, "", 30c030]
          template: "14|@sol_o|21"
    """, groesse="[128, 24]", name="a.yaml")
    b = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 24]
          row_colors: "ffff00, , 30c030"
          template: "14|@sol_o|21"
    """, groesse="[128, 24]", name="b.yaml")
    assert a.widgets[0].row_colors == b.widgets[0].row_colors
    assert list(zeichne(a).bild.getdata()) == list(zeichne(b).bild.getdata())


def test_krumme_farbe_wird_beim_laden_abgelehnt(tmp_path):
    """Nicht erst beim Zeichnen: dort käme jeden Frame eine Ausnahme, ohne die Stelle."""
    import pytest

    from panel.config import ConfigError
    with pytest.raises(ConfigError) as e:
        beschreibung(tmp_path, """
            - type: series
              at: [0, 0]
              size: [128, 24]
              row_colors: [ffff00, keinefarbe]
              template: "14|@sol_o|21"
        """, groesse="[128, 24]")
    assert "row_colors[1]" in str(e.value)


def test_unbekannte_schrift_kostet_nicht_die_kachel(tmp_path):
    """Sie fällt auf die Schrift der Kachel zurück — und wird gemeldet."""
    panel = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 24]
          row_fonts: ["", "", gibtesnicht]
          template: "14|@sol_o|21, 15|@sol_o|20"
    """, groesse="[128, 24]")
    ergebnis = zeichne(panel)
    assert any("gibtesnicht" in f for f in ergebnis.fehler)
    assert ergebnis.bild.getbbox() is not None


def test_ohne_stilangaben_bleibt_alles_wie_bisher(tmp_path):
    ohne = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 24]
          color: ffffff
          template: "14|@sol_o|21"
    """, groesse="[128, 24]", name="o.yaml")
    leer = beschreibung(tmp_path, """
        - type: series
          at: [0, 0]
          size: [128, 24]
          color: ffffff
          row_colors: ["", "", ""]
          row_fonts: ["", "", ""]
          template: "14|@sol_o|21"
    """, groesse="[128, 24]", name="l.yaml")
    assert list(zeichne(ohne).bild.getdata()) == list(zeichne(leer).bild.getdata())
