"""Die Meldezeile als Widget-Typ.

Sie war bis 0.12.6 ein Sonderfall: ein eigener Block je Anzeige, gezeichnet nach allem
anderen, mit einem eigenen Weg in den Transport. Seit 0.13.0 ist sie eine Kachel wie jede
andere — und genau das ist die Stelle, an der ein Umbau still etwas kaputtmacht:

1. Der alte Block muss WEITER funktionieren, und zwar pixelgleich. Eine Uebersetzung, die
   das Bild um eine Zeile verschiebt, faellt am Schreibtisch nicht auf.
2. Die Zeichenreihenfolge. Frueher lag die Meldung IMMER oben, weil sie zuletzt gezeichnet
   wurde. Als Kachel im Grundbild laege sie unter den Screen-Gruppen.
3. Die Zuordnung Meldung -> Zeile. Ein Kanal, den keine Zeile fuehrt, darf die Meldung
   nicht verschlucken — der Dienst haette „ok" gemeldet und niemand saehe etwas.
"""
import textwrap

import pytest

from panel.config import ConfigError, lade
from panel.fonts import FontRegistry
from panel.icons import IconRegistry
from panel.render import Renderer


def beschreibung(tmp_path, rumpf, name="aton.yaml"):
    pfad = tmp_path / name
    pfad.write_text(textwrap.dedent(rumpf).strip("\n"), encoding="utf-8")
    return lade(str(pfad))


class Quelle:
    """Zustandsquelle fuer die Vorlagen — hier reicht ein festes dict."""

    def __init__(self, **zustaende):
        self.zustaende = zustaende

    def state(self, eid):
        return self.zustaende.get(eid)

    def attr(self, eid, name):
        return None


def zeichne(panel, notiz=None, quelle=None):
    r = Renderer(panel, quelle or Quelle(), FontRegistry(), IconRegistry())
    return r.frame(notiz=notiz)


ALTER_BLOCK = """
panels:
  - id: t
    name: T
    host: 1.2.3.4
    size: [64, 16]
    notify:
      region: [0, 8, 64, 8]
"""

NEUES_WIDGET = """
panels:
  - id: t
    name: T
    host: 1.2.3.4
    size: [64, 16]
    widgets:
      - type: notify
        at: [0, 8]
        size: [64, 8]
"""


# ==========================================================================
#  Der alte Block bleibt eine gueltige Schreibweise
# ==========================================================================
def test_block_und_widget_ergeben_dasselbe_bild(tmp_path):
    alt = beschreibung(tmp_path, ALTER_BLOCK, "alt.yaml").panels[0]
    neu = beschreibung(tmp_path, NEUES_WIDGET, "neu.yaml").panels[0]

    notiz = {"text": "Post da"}
    assert list(zeichne(alt, notiz).bild.getdata()) == list(zeichne(neu, notiz).bild.getdata())


def test_block_wird_zu_einer_meldezeile(tmp_path):
    panel = beschreibung(tmp_path, ALTER_BLOCK).panels[0]

    # Uebersetzt, aber NICHT in `widgets`: dort zaehlt der Listenindex als Pfad in die
    # YAML-Datei, und `panels[0].widgets[0]` gibt es in dieser Beschreibung nicht.
    assert panel.widgets == []
    assert [w.pfad for w in panel.overlays] == ["panels[0].notify"]
    assert [w.type for w in panel.meldezeilen] == ["notify"]


def test_leere_meldung_zeichnet_nichts(tmp_path):
    """Ohne anliegende Meldung bleibt die Zeile leer — kein schwarzer Balken."""
    panel = beschreibung(tmp_path, NEUES_WIDGET).panels[0]
    assert zeichne(panel).bild.getbbox() is None


# ==========================================================================
#  Ebenen
# ==========================================================================
UEBERLAPPUNG = """
panels:
  - id: t
    name: T
    host: 1.2.3.4
    size: [64, 16]
    widgets:
      - type: notify
        at: [0, 0]
        size: [64, 8]
        {ebene}
    screen_groups:
      - id: g
        region: [0, 0, 64, 8]
        screens:
          - name: s
            widgets:
              - type: rect
                at: [0, 0]
                size: [64, 8]
                bg: '0000ff'
"""


def test_meldezeile_liegt_ueber_der_screen_gruppe(tmp_path):
    """Die Meldung ueberdeckt den Screen — aber nur mit `layer`.

    ⚠ Der Gegentest steht bewusst daneben: ohne Ebene GEWINNT der Screen, und das ist
    kein Fehler, sondern die Reihenfolge der Listen. Wer das fuer einen Bug haelt und
    „notify zeichnet immer zuletzt" einbaut, nimmt einem bewussten Aufbau die Wahl.
    """
    panel = beschreibung(tmp_path, UEBERLAPPUNG.format(ebene="layer: 1")).panels[0]
    bild = zeichne(panel, {"text": "hi"}).bild
    assert bild.getpixel((60, 1)) != (0, 0, 255)

    panel = beschreibung(tmp_path, UEBERLAPPUNG.format(ebene="")).panels[0]
    bild = zeichne(panel, {"text": "hi"}).bild
    assert bild.getpixel((60, 1)) == (0, 0, 255)


def test_alter_block_liegt_weiter_oben_auf(tmp_path):
    """Der Block hatte seine Ebene nie aufgeschrieben — die Uebersetzung muss sie kennen."""
    panel = beschreibung(tmp_path, """
        panels:
          - id: t
            name: T
            host: 1.2.3.4
            size: [64, 16]
            notify:
              region: [0, 0, 64, 8]
            screen_groups:
              - id: g
                region: [0, 0, 64, 8]
                screens:
                  - name: s
                    widgets:
                      - type: rect
                        at: [0, 0]
                        size: [64, 8]
                        bg: '0000ff'
    """).panels[0]
    assert zeichne(panel, {"text": "hi"}).bild.getpixel((60, 1)) != (0, 0, 255)


# ==========================================================================
#  Kanaele und Stufen
# ==========================================================================
ZWEI_ZEILEN = """
panels:
  - id: t
    name: T
    host: 1.2.3.4
    size: [64, 16]
    widgets:
      - type: notify
        at: [0, 0]
        size: [64, 8]
      - type: notify
        at: [0, 8]
        size: [64, 8]
        channel: warnungen
"""


def zeile_belegt(bild, y):
    return any(bild.getpixel((x, y)) != (0, 0, 0) for x in range(bild.width))


def test_kanal_landet_in_seiner_zeile(tmp_path):
    panel = beschreibung(tmp_path, ZWEI_ZEILEN).panels[0]

    bild = zeichne(panel, [{"text": "Regen", "channel": "warnungen"}]).bild
    assert not zeile_belegt(bild, 2)
    assert zeile_belegt(bild, 10)

    bild = zeichne(panel, [{"text": "Post da"}]).bild
    assert zeile_belegt(bild, 2)
    assert not zeile_belegt(bild, 10)


def test_beide_zeilen_gleichzeitig(tmp_path):
    """Der eigentliche Gewinn: zwei Meldungen nebeneinander.

    Vorher waehlte `_aktive_notiz` EINE aus, die zweite war unsichtbar.
    """
    panel = beschreibung(tmp_path, ZWEI_ZEILEN).panels[0]
    bild = zeichne(panel, [{"text": "Regen", "level": "warning", "channel": "warnungen"},
                           {"text": "Post da"}]).bild
    assert zeile_belegt(bild, 2)
    assert zeile_belegt(bild, 10)


def test_unbekannter_kanal_verschwindet_nicht(tmp_path):
    """Tippfehler im Kanal: die Meldung landet in der Hauptzeile, mit Vermerk."""
    panel = beschreibung(tmp_path, ZWEI_ZEILEN).panels[0]
    ergebnis = zeichne(panel, [{"text": "Post da", "channel": "warnunge"}])
    assert zeile_belegt(ergebnis.bild, 2)
    assert ergebnis.fehler == []


def test_anzeige_ohne_meldezeile_schweigt(tmp_path):
    """Keine Zeile ist kein Fehler.

    ⚠ Gegen die erste Fassung geschrieben, die hier meckerte: `aton.notify` ohne `panel:`
    geht ausdruecklich an ALLE Anzeigen, und die kleine 32×16 am Eingang hat keine
    Meldezeile. Gegen die laufende Beschreibung gemessen stand dadurch auf zwei von drei
    Anzeigen dauerhaft eine rote Zeile — fuer etwas, das genau so gemeint ist.
    """
    panel = beschreibung(tmp_path, """
        panels:
          - id: t
            name: T
            host: 1.2.3.4
            size: [64, 16]
    """).panels[0]
    assert zeichne(panel, [{"text": "Post da"}]).fehler == []


def test_stufenfilter(tmp_path):
    panel = beschreibung(tmp_path, """
        panels:
          - id: t
            name: T
            host: 1.2.3.4
            size: [64, 16]
            widgets:
              - type: notify
                at: [0, 0]
                size: [64, 8]
                show_levels: warning
    """).panels[0]

    assert not zeile_belegt(zeichne(panel, [{"text": "Post da"}]).bild, 2)
    ergebnis = zeichne(panel, [{"text": "Regen", "level": "warning"}])
    assert zeile_belegt(ergebnis.bild, 2)
    assert ergebnis.fehler == []

    # Was nirgends unterkommt, wird vermerkt — sonst sucht man den Fehler im Dienst.
    assert any("keine passende Meldezeile" in f
               for f in zeichne(panel, [{"text": "Post da"}]).fehler)


def test_stufenfilter_auf_unbekannte_stufe_wird_abgelehnt(tmp_path):
    """Eine Zeile, die auf eine Stufe filtert, die es nicht gibt, bliebe fuer immer leer."""
    with pytest.raises(ConfigError) as e:
        beschreibung(tmp_path, """
            panels:
              - id: t
                name: T
                host: 1.2.3.4
                size: [64, 16]
                widgets:
                  - type: notify
                    at: [0, 0]
                    size: [64, 8]
                    show_levels: warnung
        """)
    assert "warnung" in str(e.value)


def test_stufen_aller_zeilen_zaehlen(tmp_path):
    """`aton.notify` nimmt eine Stufe an, sobald IRGENDEINE Zeile sie kennt."""
    panel = beschreibung(tmp_path, """
        panels:
          - id: t
            name: T
            host: 1.2.3.4
            size: [64, 16]
            widgets:
              - type: notify
                at: [0, 0]
                size: [64, 8]
              - type: notify
                at: [0, 8]
                size: [64, 8]
                channel: alarm
                levels:
                  alarm:
                    bg: 'ff0000'
                    fg: 'ffffff'
    """).panels[0]
    assert panel.notify_levels == {"info", "warning", "alarm"}


# ==========================================================================
#  Laufschrift
# ==========================================================================
def test_lange_meldung_laeuft_mit_der_flaeche_ihrer_zeile(tmp_path):
    """Der Transport braucht die Flaeche der ZEILE, nicht die des alten Blocks."""
    panel = beschreibung(tmp_path, ZWEI_ZEILEN).panels[0]
    lang = "x" * 40
    ergebnis = zeichne(panel, [{"text": lang, "channel": "warnungen"}])

    assert len(ergebnis.scrolls) == 1
    assert ergebnis.scrolls[0].region == (0, 8, 64, 8)
    assert ergebnis.scrolls[0].text == lang
    # Der Bildspeicher bleibt an der Stelle schwarz — WLED zeichnet darueber.
    assert not zeile_belegt(ergebnis.bild, 10)


def test_zwei_laufschriften_gleichzeitig(tmp_path):
    """Seit 0.21.1 laeuft jede Meldezeile auf ihrem EIGENEN Segment.

    ⚠ Dieser Test stand vorher genau andersherum da („nur eine, und das wird gesagt").
    Die Grenze war Atons, nicht WLEDs: am Quelltext von WLED-MM geprueft ist `SEGENV` das
    Segment selbst (`FX.h`: `#define SEGENV strip._segments[strip.getCurrSegmentId()]`),
    Scroll-Offset, Farbschritt und Taktung liegen also je Segment getrennt, und
    `service()` bedient sie in Index-Reihenfolge. MAX_NUM_SEGMENTS ist auf ESP32 32.
    """
    panel = beschreibung(tmp_path, ZWEI_ZEILEN).panels[0]
    lang = "x" * 40
    ergebnis = zeichne(panel, [{"text": lang, "channel": "warnungen"},
                               {"text": lang}])

    assert len(ergebnis.scrolls) == 2, "beide Zeilen laufen"
    segmente = sorted(s.segment for s in ergebnis.scrolls)
    assert len(set(segmente)) == 2, "und zwar auf verschiedenen Segmenten"
    assert segmente == [panel.scroll_segment, panel.scroll_segment + 1]
    assert not any("Scroll-Segment" in f for f in ergebnis.fehler), \
        "die alte Absage darf nicht mehr kommen"
    # Der Bildspeicher bleibt an beiden Stellen schwarz — WLED zeichnet darueber.
    assert not zeile_belegt(ergebnis.bild, 10)


def test_segmente_haengen_an_der_zeile_nicht_an_der_meldung(tmp_path):
    """Stabil zugeteilt: Zeile 2 behaelt ihr Segment, auch wenn Zeile 1 gerade schweigt.

    ★ Sonst wuerde WLED die laufende Animation neu starten, sobald die andere Zeile
    anfaengt oder aufhoert — der Scroll-Offset haengt am Segment.
    """
    panel = beschreibung(tmp_path, ZWEI_ZEILEN).panels[0]
    lang = "x" * 40
    nur_warnung = zeichne(panel, [{"text": lang, "channel": "warnungen"}])
    beide = zeichne(panel, [{"text": lang, "channel": "warnungen"}, {"text": lang}])

    seg_allein = nur_warnung.scrolls[0].segment
    seg_zusammen = [s.segment for s in beide.scrolls
                    if s.region == nur_warnung.scrolls[0].region][0]
    assert seg_allein == seg_zusammen


# ==========================================================================
#  Sichtbarkeitsbedingung — jetzt an jeder Kachel
# ==========================================================================
def test_visible_when_gilt_fuer_jede_kachel(tmp_path):
    panel = beschreibung(tmp_path, """
        panels:
          - id: t
            name: T
            host: 1.2.3.4
            size: [64, 16]
            widgets:
              - type: rect
                at: [0, 0]
                size: [64, 8]
                bg: '0000ff'
                visible_when: "{{ is_state('binary_sensor.da', 'on') }}"
    """).panels[0]

    assert zeichne(panel, quelle=Quelle(**{"binary_sensor.da": "off"})).bild.getpixel((1, 1)) \
        == (0, 0, 0)
    assert zeichne(panel, quelle=Quelle(**{"binary_sensor.da": "on"})).bild.getpixel((1, 1)) \
        == (0, 0, 255)


def test_kaputte_bedingung_zeichnet_trotzdem(tmp_path):
    """Eine Kachel, die wegen eines Tippfehlers in der Bedingung fehlt, sucht man im Bild."""
    panel = beschreibung(tmp_path, """
        panels:
          - id: t
            name: T
            host: 1.2.3.4
            size: [64, 16]
            widgets:
              - type: rect
                at: [0, 0]
                size: [64, 8]
                bg: '0000ff'
                visible_when: "{{ kaputt( }}"
    """).panels[0]
    ergebnis = zeichne(panel)
    assert ergebnis.bild.getpixel((1, 1)) == (0, 0, 255)
    assert any("visible_when" in f for f in ergebnis.fehler)
