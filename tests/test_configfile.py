"""Reading and writing the user's description file.

This is the module with the highest damage potential in the whole app: it edits a file a
human wrote and maintains by hand. A mistake here does not show up as a wrong pixel — it
shows up weeks later as lost comments, a lost edit, or a backup folder that grew without
bound. None of that is visible on the panel.
"""
import os
import time

import pytest

from panel import configfile


BESCHREIBUNG = """\
# ==========================================================================
#  Aton — description of the panels
#  This comment must survive every save.
# ==========================================================================
panels:
  - id: wohnzimmer          # trailing comment, also worth keeping
    host: 192.168.1.50
    interval: 5
    # A comment between two keys is the easiest one to lose
    brightness:
      entity: input_number.bri
      default: 128
    widgets:
      - type: text
        at: [0, 0]
"""


@pytest.fixture
def datei(tmp_path):
    p = tmp_path / "aton.yaml"
    p.write_text(BESCHREIBUNG, encoding="utf-8")
    return str(p)


# ── Kommentare ───────────────────────────────────────────────────────────────

def test_speichern_erhaelt_alle_kommentare(datei):
    """The whole point of `verschmelze`: change a value, keep everything else."""
    daten, mtime, _ = configfile.lese(datei)
    entwurf = {"panels": [{"id": "wohnzimmer", "host": "192.168.1.50", "interval": 5,
                           "brightness": {"entity": "input_number.bri", "default": 23},
                           "widgets": [{"type": "text", "at": [0, 0]}]}]}
    configfile.schreibe(datei, configfile.verschmelze(daten, entwurf), mtime)

    text = open(datei, encoding="utf-8").read()
    assert "This comment must survive every save." in text
    assert "trailing comment, also worth keeping" in text
    assert "A comment between two keys" in text
    assert "default: 23" in text          # and the change did land


def test_nur_das_geaenderte_wird_angefasst(datei):
    """A save that changes nothing must leave the file byte-for-byte identical."""
    vorher = open(datei, encoding="utf-8").read()
    daten, mtime, _ = configfile.lese(datei)
    configfile.schreibe(datei, configfile.verschmelze(daten, daten), mtime)
    assert open(datei, encoding="utf-8").read() == vorher


def test_zahlenschluessel_werden_nicht_zu_zeichenketten(datei):
    """The browser sends JSON, where object keys are always strings.

    Without the mapping back, `steps: {337.5: wind_n}` would become `"337.5"` on every
    save — functionally identical, so nobody notices, while the file silently churns.
    """
    daten, _, _ = configfile.lese(datei)
    daten["panels"][0]["steps"] = {337.5: "wind_n"}
    verschmolzen = configfile.verschmelze(daten, {"panels": [{**{k: v for k, v in
                                          daten["panels"][0].items() if k != "steps"},
                                          "steps": {"337.5": "wind_n"}}]})
    schluessel = list(verschmolzen["panels"][0]["steps"])
    assert schluessel == [337.5], f"Schluesseltyp gekippt: {schluessel!r}"


# ── Der Wächter gegen gleichzeitiges Bearbeiten ──────────────────────────────

def test_fremde_aenderung_wird_nicht_ueberschrieben(datei):
    """Someone edited the file in VS Code while the configurator had it open."""
    daten, mtime, _ = configfile.lese(datei)
    time.sleep(0.01)
    with open(datei, "a", encoding="utf-8") as fh:
        fh.write("\n# von Hand angehaengt\n")

    with pytest.raises(configfile.SchreibFehler):
        configfile.schreibe(datei, daten, mtime)
    assert "von Hand angehaengt" in open(datei, encoding="utf-8").read()


def test_ohne_erwartete_mtime_wird_geschrieben(datei):
    """The guard is opt-in — callers that know better may skip it."""
    daten, _, _ = configfile.lese(datei)
    configfile.schreibe(datei, daten, None)
    assert os.path.exists(datei)


# ── Sicherungen ──────────────────────────────────────────────────────────────

def test_jeder_schreibvorgang_legt_eine_sicherung_an(datei):
    daten, mtime, _ = configfile.lese(datei)
    sicherung = configfile.schreibe(datei, daten, mtime)
    assert os.path.exists(sicherung)
    assert open(sicherung, encoding="utf-8").read() == BESCHREIBUNG


def test_sicherungen_liegen_im_unterordner_nicht_neben_der_datei(datei):
    """Twenty .bak files next to configuration.yaml make HA's file browser unusable."""
    daten, mtime, _ = configfile.lese(datei)
    sicherung = configfile.schreibe(datei, daten, mtime)
    assert os.path.dirname(sicherung) != os.path.dirname(datei)
    daneben = [f for f in os.listdir(os.path.dirname(datei)) if ".bak-" in f]
    assert daneben == []


def test_aufraeumen_behaelt_die_juengsten(datei):
    ordner = configfile._sicherungsordner(datei)
    name = os.path.basename(datei)
    for i in range(25):
        open(os.path.join(ordner, f"{name}.bak-202608{i:02d}-120000"), "w").close()

    weg = configfile.sicherungen_aufraeumen(datei, behalten=20)
    rest = sorted(f for f in os.listdir(ordner) if ".bak-" in f)
    assert weg == 5 and len(rest) == 20
    assert rest[-1].endswith("20260824-120000")     # the newest one stayed


def test_aufraeumen_sortiert_nach_name_nicht_nach_mtime(datei):
    """`copy2` carries the source mtime over, so a backup can be older than its content.

    Sorting by mtime would then throw away the wrong one — the timestamp in the name is
    the only reliable order.
    """
    ordner = configfile._sicherungsordner(datei)
    name = os.path.basename(datei)
    jung = os.path.join(ordner, f"{name}.bak-20260807-120000")
    alt = os.path.join(ordner, f"{name}.bak-20260101-120000")
    open(jung, "w").close()
    open(alt, "w").close()
    os.utime(jung, (0, 0))                 # the NEW one gets an ancient mtime

    configfile.sicherungen_aufraeumen(datei, behalten=1)
    assert os.path.exists(jung) and not os.path.exists(alt)


# ── Schreiben ohne halbe Dateien ─────────────────────────────────────────────

def test_keine_zwischendateien_bleiben_liegen(datei):
    daten, mtime, _ = configfile.lese(datei)
    configfile.schreibe(datei, daten, mtime)
    reste = [f for f in os.listdir(os.path.dirname(datei)) if f.startswith(".aton_")]
    assert reste == []
