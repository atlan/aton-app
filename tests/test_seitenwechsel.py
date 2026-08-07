"""Page rotation: which page of a screen is showing right now.

The rule has two properties that are easy to break and hard to notice:

1. It is computed from the CLOCK, not from a frame counter. A counter would be advanced
   by the configurator's preview as well, and two panels would drift apart over time.
2. Pages may have individual durations (`zyklen`, since 0.10.0). With equal durations the
   result must be bit-for-bit what it was before that feature existed — otherwise every
   existing description would start rotating differently after an update.

Property 2 is the reason for the sweep over 20 000 points in time: it is the cheap proof
that a behaviour-preserving change really preserved behaviour.
"""
import types

import pytest

from panel.config import Screen, Seite
from panel.render import Renderer


INTERVALL = 5.0


def renderer(interval=INTERVALL):
    """A Renderer shell — `_seite_waehlen` only needs `self.panel.interval`."""
    r = Renderer.__new__(Renderer)
    r.panel = types.SimpleNamespace(interval=interval)
    return r


def screen(*takte, wechsel=1):
    """A screen with one page per entry; entry 0 means 'inherit from the screen'."""
    return Screen(name="s", wechsel_zyklen=wechsel,
                  seiten=[Seite(name=f"p{i}", zyklen=z) for i, z in enumerate(takte)])


def alte_formel(anzahl, wechsel, t, interval=INTERVALL):
    """The rule as it was before per-page durations existed."""
    return int(t / (wechsel * interval)) % anzahl


# ── Rückwärtskompatibilität ──────────────────────────────────────────────────

@pytest.mark.parametrize("anzahl", [2, 3, 5])
@pytest.mark.parametrize("wechsel", [1, 2, 7])
def test_ohne_eigene_takte_wie_die_alte_formel(anzahl, wechsel, monkeypatch):
    """Pages without their own `zyklen` must rotate exactly as they always did."""
    s = screen(*([0] * anzahl), wechsel=wechsel)
    r = renderer()
    for t in range(0, 20_000, 7):
        monkeypatch.setattr("panel.render.time.time", lambda t=t: float(t))
        assert r._seite_waehlen(s, None) == alte_formel(anzahl, wechsel, t)


# ── Ungleiche Standzeiten ────────────────────────────────────────────────────

def test_ungleiche_takte_ergeben_die_gewuenschte_folge(monkeypatch):
    """2 cycles for page A, 1 for page B → A A B, repeating."""
    s = screen(2, 1)
    r = renderer()
    folge = []
    for zyklus in range(9):
        monkeypatch.setattr("panel.render.time.time", lambda z=zyklus: z * INTERVALL)
        folge.append(r._seite_waehlen(s, None))
    assert folge == [0, 0, 1, 0, 0, 1, 0, 0, 1]


def test_seite_ohne_angabe_erbt_vom_screen(monkeypatch):
    """A page with no value of its own uses the screen's — mixing is allowed."""
    s = screen(3, 0, wechsel=1)          # A: 3 cycles, B: inherits 1
    r = renderer()
    folge = []
    for zyklus in range(8):
        monkeypatch.setattr("panel.render.time.time", lambda z=zyklus: z * INTERVALL)
        folge.append(r._seite_waehlen(s, None))
    assert folge == [0, 0, 0, 1, 0, 0, 0, 1]


# ── Der Hauptschalter ────────────────────────────────────────────────────────

def test_wechsel_null_haelt_alles_an(monkeypatch):
    """`wechsel_zyklen: 0` means 'first page only' — even if pages carry numbers.

    Without this the documented meaning would be true or false depending on what the
    pages happen to contain.
    """
    s = screen(2, 1, wechsel=0)
    r = renderer()
    for t in range(0, 100, 5):
        monkeypatch.setattr("panel.render.time.time", lambda t=t: float(t))
        assert r._seite_waehlen(s, None) == 0


def test_eine_einzige_seite_wechselt_nie(monkeypatch):
    s = screen(0, wechsel=5)
    monkeypatch.setattr("panel.render.time.time", lambda: 12345.0)
    assert renderer()._seite_waehlen(s, None) == 0


# ── Die Vorgabe aus dem Konfigurator ─────────────────────────────────────────

def test_vorgabe_haelt_die_uhr_an(monkeypatch):
    """The configurator passes the page selected in its tree; the clock must not win.

    Without this, clicking "Feuchte" in the tree still showed temperatures — whichever
    page happened to be due — and one goes looking for the mistake in the description.
    """
    s = screen(0, 0, 0, wechsel=1)
    monkeypatch.setattr("panel.render.time.time", lambda: 0.0)   # page 0 would be due
    assert renderer()._seite_waehlen(s, 2) == 2


def test_vorgabe_wird_zurechtgebogen_statt_abgewiesen(monkeypatch):
    """While editing, the tree may point at a page the draft no longer has."""
    s = screen(0, 0, wechsel=1)
    monkeypatch.setattr("panel.render.time.time", lambda: 0.0)
    assert renderer()._seite_waehlen(s, 99) == 1     # clamped to the last one
    assert renderer()._seite_waehlen(s, -5) == 0
