"""Brightness: setting it, and reporting it back honestly.

Two bugs lived here, both silent:

* Before 0.5.x `setze_helligkeit` only wrote an app-internal value, which `helligkeit()`
  reads *only* when no `brightness.entity` is configured. With an entity the slider was
  simply without effect — nothing failed, nothing was logged, the panel just did not
  change.
* Before 0.10.2 the endpoint read the value back straight after writing it. That read
  goes through HA's state mirror, which only catches up when the `state_changed` event
  arrives — so the answer reported the *previous* value, and the next `/api/panels` poll
  contradicted the slider.

Both are the kind of mistake that looks like "the click did not work".
"""
import asyncio
import time
import types

import pytest

from panel.display import Display


class HaAttrappe:
    """Just enough Home Assistant: a state mirror and a service call."""

    def __init__(self, ok=True):
        self.werte = {}
        self.ok = ok
        self.rufe = []

    def state(self, eid):
        return self.werte.get(eid)

    async def rufe_dienst(self, eid, dienst, daten=None):
        self.rufe.append((eid, dienst, daten))
        return self.ok


def anzeige(entity, ha_ok=True, default=128):
    d = Display.__new__(Display)
    d.cfg = types.SimpleNamespace(id="entry", brightness_entity=entity,
                                  brightness_default=default)
    d.ha = HaAttrappe(ha_ok)
    d._eigene_helligkeit = default
    d._gesetzte_helligkeit = (None, 0.0)
    d._sofort = types.SimpleNamespace(set=lambda: None)
    return d


EID = "input_number.entrymatrixbri"


def lauf(coro):
    """`asyncio.run` statt pytest-asyncio — spart der Testsuite eine Abhaengigkeit,
    und die geprueften Funktionen sind ohnehin einzelne Aufrufe ohne Ereignisschleife."""
    return asyncio.run(coro)


# ── Der gesetzte Wert wird gemeldet, nicht zurückgelesen ─────────────────────

def test_meldet_den_gesetzten_wert_sofort():
    d = anzeige(EID)
    d.ha.werte[EID] = "23"
    assert lauf(d.setze_helligkeit(30)) == 30
    assert d.helligkeit() == 30, "meldete den Wert von vorher — genau der alte Fehler"


def test_nach_der_bestaetigung_gilt_wieder_der_spiegel():
    d = anzeige(EID)
    d.ha.werte[EID] = "23"
    lauf(d.setze_helligkeit(30))
    d.ha.werte[EID] = "30"                      # HA hat nachgezogen
    assert d.helligkeit() == 30
    assert d._gesetzte_helligkeit[0] is None, "Merker wurde nicht abgeraeumt"


def test_notbremse_nach_fristablauf():
    """If confirmation never arrives, the display must not keep claiming the value."""
    d = anzeige(EID)
    d.ha.werte[EID] = "23"
    lauf(d.setze_helligkeit(30))
    d._gesetzte_helligkeit = (30, time.monotonic() - 1)
    assert d.helligkeit() == 23


# ── Es wird dorthin geschrieben, wo auch gelesen wird ────────────────────────

def test_mit_entitaet_wird_der_dienst_gerufen():
    d = anzeige(EID)
    lauf(d.setze_helligkeit(30))
    assert d.ha.rufe == [(EID, "set_value", {"value": 30})]


def test_ohne_entitaet_bleibt_es_app_intern():
    d = anzeige(None)
    assert lauf(d.setze_helligkeit(30)) == 30
    assert d.helligkeit() == 30
    assert d.ha.rufe == []


# ── Grenzen und Fehlerfälle ──────────────────────────────────────────────────

@pytest.mark.parametrize("eingabe,erwartet", [(300, 255), (0, 1), (-5, 1), ("42", 42),
                                              (42.7, 42)])
def test_wird_auf_1_bis_255_begrenzt(eingabe, erwartet):
    assert lauf(anzeige(None).setze_helligkeit(eingabe)) == erwartet


@pytest.mark.parametrize("unsinn", ["abc", None, {}, ""])
def test_unbrauchbare_eingabe_gibt_none(unsinn):
    assert lauf(anzeige(None).setze_helligkeit(unsinn)) is None


def test_nicht_setzbare_domain_gibt_none():
    """A light cannot be set with `set_value` — better to say so than to pretend."""
    d = anzeige("light.irgendwas")
    assert lauf(d.setze_helligkeit(30)) is None
    assert d.ha.rufe == []


def test_ablehnung_durch_ha_gibt_none():
    d = anzeige(EID, ha_ok=False)
    assert lauf(d.setze_helligkeit(30)) is None
    assert d._gesetzte_helligkeit[0] is None, "abgelehnter Wert darf nicht gelten"


# ── Lesen ohne brauchbaren Zustand ───────────────────────────────────────────

@pytest.mark.parametrize("zustand", [None, "unavailable", "unknown", ""])
def test_unlesbarer_zustand_faellt_auf_die_vorgabe(zustand):
    d = anzeige(EID, default=77)
    d.ha.werte[EID] = zustand
    assert d.helligkeit() == 77
