"""Wann gesendet wird — und was als Sendefehler zaehlt.

Am 14.08.2026 an der Anlage gemessen, und beides war teuer:

* **Einschalten.** Zwischen „Strom an" und „WLED antwortet" liegen 18–20 s. Die App
  startete auf der Sekunde des Stromschalters (ueber `gate.fallback`) und schickte in
  dieser Luecke ein Vollbild — in acht Bloecken, also acht Meldungen fuer einen
  Sachverhalt. Im Protokoll: `11:21:21` einmal, `11:21:23` siebenmal.
* **Stromausfall.** Die Entry-Matrix stand 7,5 h stromlos auf dem Schreibtisch. Ihr Tor
  meldete `unavailable`, ein Rueckfall ist dort nicht konfiguriert, also griff die Regel
  „im Zweifel zeichnen" — und buchte **5888 Sendefehler** fuer eine einzige Ursache.

Die Tests halten beides fest: die Wartezeit auf das Tor, den Abbruch nach dem ersten
gescheiterten Block, den Rueckzug und die Trennung zwischen Messung und Stoerung.
"""
import asyncio
import json
import time
import types

import pytest

from panel.display import NOTAUSGANG_S, RUECKZUG_MAX_S, Display
from panel.wled import Unerreichbar, WledTransport

TOR = "light.matrix_power"


class HaAttrappe:
    def __init__(self):
        self.werte = {}

    def state(self, eid):
        return self.werte.get(eid)


def anzeige(gate=TOR, intervall=5):
    d = Display.__new__(Display)
    d.cfg = types.SimpleNamespace(id="wohnzimmer", gate_entity=gate, interval=intervall,
                                  gate_wartezeit=int(NOTAUSGANG_S))
    d.ha = HaAttrappe()
    d.transport = types.SimpleNamespace(stat=types.SimpleNamespace(erreichbar=True))
    d._tor_nicht_on_seit = 0.0
    d._naechster_versuch = 0.0
    d._rueckzug = 0.0
    return d


# ── Das Tor ist der Erreichbarkeitsmelder ────────────────────────────────────

def test_tor_meldet_on_also_wird_gesendet():
    d = anzeige()
    d.ha.werte[TOR] = "on"
    darf, probe, grund = d._sendefenster()
    assert (darf, probe, grund) == (True, False, "")


def test_waehrend_des_hochlaufs_wird_NICHT_gesendet():
    """Der Kern: 20 s Strom-ohne-WLED duerfen keinen einzigen Versuch kosten."""
    d = anzeige()
    d.ha.werte[TOR] = "unavailable"
    darf, probe, grund = d._sendefenster()
    assert darf is False, "genau hier entstanden die 8 Sendefehler je Einschaltvorgang"
    assert TOR in grund

    # Auch 20 s spaeter — der gemessene Hochlauf — noch nicht.
    d._tor_nicht_on_seit = time.time() - 20
    assert d._sendefenster()[0] is False


def test_notausgang_nach_der_wartezeit_und_zwar_als_probe():
    """Die Henne-Ei-Falle muss sich weiterhin selbst loesen koennen."""
    d = anzeige()
    d.ha.werte[TOR] = "unavailable"
    d._sendefenster()
    d._tor_nicht_on_seit = time.time() - (NOTAUSGANG_S + 1)
    darf, probe, _ = d._sendefenster()
    assert darf is True
    assert probe is True, "ein Versuch ins Ungewisse ist eine Messung, keine Stoerung"


def test_ohne_tor_wird_wie_bisher_sofort_gesendet():
    d = anzeige(gate=None)
    assert d._sendefenster() == (True, False, "")


def test_ruecksprung_wenn_das_tor_wieder_on_meldet():
    d = anzeige()
    d.ha.werte[TOR] = "unavailable"
    d._sendefenster()
    assert d._tor_nicht_on_seit
    d.ha.werte[TOR] = "on"
    assert d._sendefenster()[0] is True
    assert d._tor_nicht_on_seit == 0.0, "sonst laeuft die Wartezeit beim naechsten Mal ab"


# ── Rueckzug ────────────────────────────────────────────────────────────────

def test_rueckzug_verdoppelt_und_deckelt():
    d = anzeige(intervall=5)
    d.transport.stat.erreichbar = False
    dauern = []
    for _ in range(8):
        d._rueckzug_fortschreiben()
        dauern.append(d._rueckzug)
    assert dauern[:4] == [10, 20, 40, 60]
    assert max(dauern) == RUECKZUG_MAX_S


def test_rueckzug_sperrt_den_naechsten_takt():
    d = anzeige()
    d.ha.werte[TOR] = "on"
    d.transport.stat.erreichbar = False
    d._rueckzug_fortschreiben()
    darf, _, grund = d._sendefenster()
    assert darf is False and "Rueckzug" in grund


def test_erfolg_hebt_den_rueckzug_sofort_auf():
    d = anzeige()
    d.transport.stat.erreichbar = False
    d._rueckzug_fortschreiben()
    d.transport.stat.erreichbar = True
    d._rueckzug_fortschreiben()
    assert (d._rueckzug, d._naechster_versuch) == (0.0, 0.0)
    d.ha.werte[TOR] = "on"
    assert d._sendefenster()[0] is True


# ── Der Abbruch im Transport ────────────────────────────────────────────────

class SitzungsAttrappe:
    """Jeder POST scheitert — wie gegen ein stromloses Geraet."""

    def __init__(self):
        self.versuche = 0

    def post(self, *a, **kw):
        self.versuche += 1
        raise OSError("Cannot connect to host 192.168.1.50:80")


def transport():
    p = types.SimpleNamespace(id="wohnzimmer", host="192.168.1.50", width=128, height=64,
                              canvas_segment=0, scroll_segment=1, clear_segments_to=32,
                              hoechstes_scroll_segment=1, full_frame_every=60)
    return WledTransport(p)


def bild():
    from PIL import Image
    return Image.new("RGB", (128, 64))


def test_ein_gescheiterter_block_beendet_den_frame():
    t, s = transport(), SitzungsAttrappe()
    asyncio.run(t.sende(s, bild(), 128, None))
    assert s.versuche == 1, "frueher gingen alle acht Bloecke raus, jeder mit eigener Meldung"
    assert t.stat.fehler == 1
    assert t.stat.erreichbar is False


def test_nach_dem_abbruch_folgt_wieder_ein_vollbild():
    t, s = transport(), SitzungsAttrappe()
    asyncio.run(t.sende(s, bild(), 128, None))
    assert t._letztes is None, "sonst rechnet die Differenz gegen ein Bild, das dort nie ankam"
    assert t.stat.frames == 0 and t.stat.vollbilder == 0, "nichts angekommen, nichts gezaehlt"


def test_probe_setzt_den_zustand_aber_nicht_den_zaehler():
    t, s = transport(), SitzungsAttrappe()
    asyncio.run(t.sende(s, bild(), 128, None, probe=True))
    assert t.stat.fehler == 0, "eine Messung ist kein Vorfall — sonst 5888 davon in einer Nacht"
    assert t.stat.erreichbar is False
    assert t.stat.unerreichbar_seit > 0


def test_unerreichbar_seit_bleibt_beim_ersten_zeitpunkt_stehen():
    t, s = transport(), SitzungsAttrappe()
    asyncio.run(t.sende(s, bild(), 128, None, probe=True))
    erster = t.stat.unerreichbar_seit
    time.sleep(0.01)
    asyncio.run(t.sende(s, bild(), 128, None, probe=True))
    assert t.stat.unerreichbar_seit == erster, "der Zeitpunkt darf nicht mitwandern"


def test_post_wirft_damit_der_aufrufer_gar_nicht_erst_weitermacht():
    t, s = transport(), SitzungsAttrappe()
    with pytest.raises(Unerreichbar):
        asyncio.run(t._post(s, {"seg": []}))


# ── Die Wartezeit ist je Anzeige einstellbar ────────────────────────────────

def test_eigene_wartezeit_schlaegt_die_vorgabe():
    """Der Nachweis am Geraet brauchte 95 s, die Vorgabe steht auf 90 — genau dafuer."""
    d = anzeige()
    d.cfg.gate_wartezeit = 180
    d.ha.werte[TOR] = "unavailable"
    d._sendefenster()
    d._tor_nicht_on_seit = time.time() - 120     # laenger als die Vorgabe, kuerzer als 180
    assert d._sendefenster()[0] is False
    d._tor_nicht_on_seit = time.time() - 181
    assert d._sendefenster()[0] is True


def test_wartezeit_null_verhaelt_sich_wie_frueher():
    d = anzeige()
    d.cfg.gate_wartezeit = 0
    d.ha.werte[TOR] = "unavailable"
    darf, probe, _ = d._sendefenster()
    assert (darf, probe) == (True, True)


# ── Helligkeit: der Wert allein bewegt ein stehendes Bild nicht ─────────────

class _Antwort:
    status = 200

    async def text(self):
        return ""

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class SitzungOk:
    """Jeder POST gelingt. Merkt sich, was geschickt wurde."""

    def __init__(self):
        self.pakete = []

    def post(self, url, data=None, headers=None):
        self.pakete.append(json.loads(data))
        return _Antwort()


def _hat_pixel(pakete):
    return any("i" in s and s["i"] for p in pakete for s in p.get("seg", []))


def test_helligkeitswechsel_schreibt_die_pixel_neu():
    """Am 14.08.2026 gemessen: die TV-Matrix aendert 0 Pixel je Takt. Ohne Vollbild
    kaeme nur der Wert an, und die Flaeche bliebe sichtbar unveraendert."""
    t, s = transport(), SitzungOk()
    b = bild()
    asyncio.run(t.sende(s, b, 128, None))          # erstes Bild = Vollbild
    s.pakete.clear()
    asyncio.run(t.sende(s, b, 128, None))          # identisch: nichts zu tun
    assert not _hat_pixel(s.pakete), "unveraendertes Bild darf keine Pixel schicken"
    s.pakete.clear()
    asyncio.run(t.sende(s, b, 40, None))           # nur die Helligkeit aendert sich
    assert _hat_pixel(s.pakete), "ohne neu geschriebene Pixel wirkt die Helligkeit nicht"
    assert any(x.get("bri") == 40 for p in s.pakete for x in p.get("seg", [])), \
        "und der neue Wert muss natuerlich mit"
