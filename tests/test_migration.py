"""Veraltete Namen umschreiben — beim Laden im Konfigurator und beim Speichern.

Der Gewinn ist klein (die Datei sagt dasselbe wie das Formular), der moegliche Schaden
gross: geschrieben wird die Datei, die jemand von Hand pflegt. Geprueft wird deshalb vor
allem, was dabei NICHT passieren darf:

* Der umbenannte Schluessel bleibt an seiner Stelle und behaelt seinen Kommentar.
* Die Bedeutung bleibt gleich — `wechsel_s` (Sekunden) wird mit demselben Bildtakt
  umgerechnet wie im Lader, sonst laeuft die Anzeige nach dem Speichern anders.
* Ein zweiter Durchlauf aendert nichts mehr.
"""
import json

import pytest

from panel import configfile, migration
from panel.config import lade


ALT = """\
# Kopfkommentar — muss jede Umbenennung ueberleben
panels:
  - id: wohnzimmer
    host: 192.168.1.50
    size: [128, 64]
    interval: 5
    widgets:
      - type: serie          # Kommentar am Typ
        at: [0, 0]
        size: [128, 24]
        template: "12|@info|3"
    screen_groups:
      - id: felder
        name: Felder
        region: [0, 27, 128, 18]
        screens:
          # Kommentar VOR dem Screen
          - name: Solar
            when: always
            wechsel_zyklen: 2      # Kommentar am alten Schluessel
            seiten:
              - name: Erzeugung
                zyklen: 2
                widgets:
                  - type: text
                    at: [0, 0]
                    size: [32, 8]
                    template: "a"
              - name: Straenge
                zyklen: 1
                widgets:
                  - type: text
                    at: [0, 0]
                    size: [32, 8]
                    template: "b"
"""


@pytest.fixture
def datei(tmp_path):
    p = tmp_path / "aton.yaml"
    p.write_text(ALT, encoding="utf-8")
    return str(p)


def speichern(pfad, entwurf):
    """Was `KonfiguratorAPI.speichern` tut — ohne Webserver."""
    vorhanden, mtime, _ = configfile.lese(pfad)
    migration.migriere(vorhanden)
    configfile.schreibe(pfad, configfile.verschmelze(vorhanden, entwurf), mtime)
    return open(pfad, encoding="utf-8").read()


def entwurf_aus(pfad):
    """Das Datenmodell, wie es der Browser bekommt: migriert und durch JSON gegangen."""
    daten, _, _ = configfile.lese(pfad)
    notizen = migration.migriere(daten)
    return json.loads(json.dumps(daten)), notizen


# ==========================================================================
#  Was umbenannt wird
# ==========================================================================
def test_alle_veralteten_namen(datei):
    entwurf, notizen = entwurf_aus(datei)
    screen = entwurf["panels"][0]["screen_groups"][0]["screens"][0]
    assert screen["page_cycles"] == 2 and "wechsel_zyklen" not in screen
    assert "pages" in screen and "seiten" not in screen
    assert screen["pages"][0]["cycles"] == 2 and "zyklen" not in screen["pages"][0]
    assert entwurf["panels"][0]["widgets"][0]["type"] == "series"
    # Jede Aenderung wird auch benannt — der Konfigurator zeigt genau diese Liste.
    assert len(notizen) == 5
    assert any("type serie → series" in n for n in notizen)
    assert any("seiten → pages" in n for n in notizen)


def test_seiten_werden_nach_der_umbenennung_noch_durchlaufen(datei):
    """★ Reihenfolgefalle: erst `seiten` → `pages`, dann in den Seiten weitermachen.

    Wer die Liste vorher einsammelt, migriert die Seiten nicht mehr — `zyklen` bliebe
    stehen und faellt erst beim naechsten Laden als veralteter Name auf.
    """
    entwurf, _ = entwurf_aus(datei)
    seiten = entwurf["panels"][0]["screen_groups"][0]["screens"][0]["pages"]
    assert [s["cycles"] for s in seiten] == [2, 1]


def test_sekunden_werden_mit_dem_bildtakt_umgerechnet(tmp_path):
    """`wechsel_s: 20` bei 5 s Bildtakt sind 4 Zyklen — dieselbe Rechnung wie im Lader."""
    p = tmp_path / "a.yaml"
    p.write_text("""\
panels:
  - id: t
    host: 1.2.3.4
    size: [64, 32]
    interval: 5
    screen_groups:
      - id: g
        name: G
        region: [0, 0, 64, 32]
        screens:
          - name: S
            when: always
            wechsel_s: 20
            pages:
              - name: P
                widgets: []
""", encoding="utf-8")
    entwurf, _ = entwurf_aus(str(p))
    assert entwurf["panels"][0]["screen_groups"][0]["screens"][0]["page_cycles"] == 4


def test_beide_namen_gesetzt_der_neue_gilt(tmp_path):
    """Genau wie im Lader: der alte wird weggeraeumt, nicht gedeutet."""
    p = tmp_path / "a.yaml"
    p.write_text("""\
panels:
  - id: t
    host: 1.2.3.4
    size: [64, 32]
    screen_groups:
      - id: g
        name: G
        region: [0, 0, 64, 32]
        screens:
          - name: S
            when: always
            wechsel_zyklen: 9
            page_cycles: 3
            widgets: []
""", encoding="utf-8")
    entwurf, notizen = entwurf_aus(str(p))
    screen = entwurf["panels"][0]["screen_groups"][0]["screens"][0]
    assert screen["page_cycles"] == 3 and "wechsel_zyklen" not in screen
    assert any("entfernt" in n for n in notizen)


def test_unfug_verhindert_das_speichern_nicht(tmp_path):
    """Ein `wechsel_s: "bald"` laesst sich nicht umrechnen — dann bleibt es stehen.

    Die Beschwerde kommt beim Laden vom Lader. Ein Speichern daran scheitern zu lassen
    waere die schlechtere Wahl: man kaeme aus dem Konfigurator nicht mehr heraus, ohne
    die Datei von Hand zu reparieren.
    """
    p = tmp_path / "a.yaml"
    p.write_text("""\
panels:
  - id: t
    host: 1.2.3.4
    size: [64, 32]
    screen_groups:
      - id: g
        name: G
        region: [0, 0, 64, 32]
        screens:
          - name: S
            when: always
            wechsel_s: bald
            widgets: []
""", encoding="utf-8")
    entwurf, notizen = entwurf_aus(str(p))
    assert entwurf["panels"][0]["screen_groups"][0]["screens"][0]["wechsel_s"] == "bald"
    assert notizen == []


# ==========================================================================
#  Was dabei nicht kaputtgehen darf
# ==========================================================================
def test_speichern_erhaelt_kommentare_und_reihenfolge(datei):
    entwurf, _ = entwurf_aus(datei)
    text = speichern(datei, entwurf)

    assert "Kopfkommentar" in text
    assert "Kommentar am Typ" in text
    assert "Kommentar VOR dem Screen" in text
    # ★ Der Kommentar hing am alten Schluessel und muss am neuen weiterhaengen.
    assert any(z.strip().startswith("page_cycles: 2")
               and "# Kommentar am alten Schluessel" in z
               for z in text.splitlines())
    # ★ Und der Schluessel bleibt an seiner Stelle — nicht ans Ende der Zuordnung.
    zeilen = [z.strip().split(":")[0] for z in text.splitlines() if z.strip()]
    assert zeilen.index("page_cycles") < zeilen.index("pages")
    assert "wechsel_zyklen" not in text and "seiten:" not in text
    assert "type: series" in text


def test_bedeutung_bleibt_gleich(datei):
    """Vorher und nachher laden — die Anzeige muss danach dasselbe tun."""
    vorher = lade(datei)
    entwurf, _ = entwurf_aus(datei)
    speichern(datei, entwurf)
    nachher = lade(datei)

    s_v = vorher.panels[0].groups[0].screens[0]
    s_n = nachher.panels[0].groups[0].screens[0]
    assert s_v.wechsel_zyklen == s_n.wechsel_zyklen
    assert [s.zyklen for s in s_v.seiten] == [s.zyklen for s in s_n.seiten]
    assert vorher.panels[0].widgets[0].type == nachher.panels[0].widgets[0].type


def test_zweiter_durchlauf_aendert_nichts(datei):
    entwurf, _ = entwurf_aus(datei)
    speichern(datei, entwurf)
    text1 = open(datei, encoding="utf-8").read()

    entwurf2, notizen2 = entwurf_aus(datei)
    assert notizen2 == []                      # nichts mehr zu tun
    speichern(datei, entwurf2)
    assert open(datei, encoding="utf-8").read() == text1


def test_ohne_veraltete_namen_bleibt_die_datei_unberuehrt(tmp_path):
    """Der haeufigste Fall: es gibt nichts umzubenennen — dann passiert auch nichts."""
    p = tmp_path / "a.yaml"
    p.write_text("""\
# nichts Veraltetes hier
panels:
  - id: t
    host: 1.2.3.4
    size: [64, 32]
    widgets:
      - type: text
        at: [0, 0]
        size: [32, 8]
        template: "a"
""", encoding="utf-8")
    vorher = p.read_text(encoding="utf-8")
    entwurf, notizen = entwurf_aus(str(p))
    assert notizen == []
    speichern(str(p), entwurf)
    assert p.read_text(encoding="utf-8") == vorher


def test_unfertige_beschreibung_stuerzt_nicht_ab():
    """Der Entwurf aus dem Browser ist waehrend des Bearbeitens auch mal halbfertig."""
    for unfug in ({}, {"panels": None}, {"panels": [None, "x"]},
                  {"panels": [{"widgets": ["x", None], "screen_groups": [{}, "x"]}]}):
        assert migration.migriere(unfug) == []
    assert migration.migriere("kein dict") == []
