"""Validating the description.

The parser is the app's front door: everything downstream trusts what comes out of it.
Two things matter and both are tested here — that valid descriptions keep loading, and
that invalid ones fail *with a usable path*. The second half is what makes a typo a
two-second fix instead of a hunt: `panels[0].screen_groups[0].screens[2].seiten[0]`
points straight at the line.

⚠ The shipped `examples/aton.yaml` is loaded as a whole. That is deliberately a
regression test for the example itself — an example that no longer parses is worse than
none, because it is the first thing a new user copies.
"""
from pathlib import Path

import pytest

from panel.config import ConfigError, lade, pruefe


BEISPIEL = Path(__file__).resolve().parents[1] / "examples" / "aton.yaml"


def anzeige(**extra):
    """The smallest description the parser accepts, plus whatever the test needs."""
    return {"panels": [{"id": "p", "host": "1.2.3.4", "size": [32, 16], **extra}]}


# ── Was gelten muss ──────────────────────────────────────────────────────────

def test_mitgeliefertes_beispiel_laedt():
    lade(str(BEISPIEL))


def test_kleinste_beschreibung_laedt():
    app = pruefe(anzeige(), "t")
    assert app.panels[0].id == "p"


# ── Pflichtfelder ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("roh,erwartet", [
    ({}, "panels"),
    ({"panels": []}, "mindestens eine"),
    ({"panels": [{"id": "p", "host": "1.2.3.4"}]}, "size"),
])
def test_fehlende_pflichtfelder_werden_benannt(roh, erwartet):
    with pytest.raises(ConfigError) as e:
        pruefe(roh, "t")
    assert erwartet in str(e.value)


# ── Tippfehler ───────────────────────────────────────────────────────────────

def test_unbekannter_schluessel_faellt_auf():
    """Silently ignoring an unknown key is the worst option: the user writes
    `wechsel_zyklem`, nothing happens, and nothing says why."""
    with pytest.raises(ConfigError) as e:
        pruefe(anzeige(widgets=[{"type": "text", "at": [0, 0], "farbe": "rot"}]), "t")
    assert "farbe" in str(e.value)


def test_der_pfad_zeigt_auf_die_stelle():
    roh = anzeige(screen_groups=[{
        "id": "g", "region": [0, 0, 32, 16],
        "screens": [{"name": "A", "pages": [{"name": "x", "cyclesn": 2}, {"name": "y"}]}],
    }])
    with pytest.raises(ConfigError) as e:
        pruefe(roh, "t")
    meldung = str(e.value)
    assert "screen_groups[0].screens[0].pages[0]" in meldung, meldung
    assert "cyclesn" in meldung


# ── Seiten und Zyklen (seit 0.10.0) ──────────────────────────────────────────

def gruppe_mit_seiten(**screen_extra):
    return anzeige(screen_groups=[{
        "id": "g", "region": [0, 0, 32, 16],
        "screens": [{"name": "A", **screen_extra}],
    }])


def test_eigene_zyklen_je_seite_werden_uebernommen():
    app = pruefe(gruppe_mit_seiten(page_cycles=1,
                                   pages=[{"name": "A", "cycles": 2},
                                           {"name": "B", "cycles": 1}]), "t")
    seiten = app.panels[0].groups[0].screens[0].seiten
    assert [(s.name, s.zyklen) for s in seiten] == [("A", 2), ("B", 1)]


def test_ohne_angabe_ist_zyklen_null():
    """0 means "inherit from the screen" — the whole point of the default."""
    app = pruefe(gruppe_mit_seiten(pages=[{"name": "A"}, {"name": "B"}]), "t")
    assert [s.zyklen for s in app.panels[0].groups[0].screens[0].seiten] == [0, 0]


def test_negative_zyklen_werden_auf_null_gezogen():
    app = pruefe(gruppe_mit_seiten(pages=[{"name": "A", "cycles": -5}]), "t")
    assert app.panels[0].groups[0].screens[0].seiten[0].zyklen == 0


def test_widgets_und_seiten_zusammen_sind_ein_fehler():
    """Both would mean two places for the same tiles — which one wins is a coin toss."""
    with pytest.raises(ConfigError) as e:
        pruefe(gruppe_mit_seiten(widgets=[], pages=[{"name": "A"}]), "t")
    assert "pages" in str(e.value)


def test_ein_screen_ohne_seiten_bekommt_genau_eine():
    """So the renderer never has to know two cases."""
    app = pruefe(gruppe_mit_seiten(widgets=[]), "t")
    seiten = app.panels[0].groups[0].screens[0].seiten
    assert len(seiten) == 1 and seiten[0].name == "A"
