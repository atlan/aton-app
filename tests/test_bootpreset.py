"""Das schwarze Boot-Preset — damit die Matrix beim Hochfahren nicht orange leuchtet.

Am 17.08.2026 an allen drei Matrizen der Anlage gemessen: ohne Boot-Preset malt WLED
beim Einschalten seine eingebaute Vorgabefarbe **RGB 255,160,0**, ein volles Orange
ueber die ganze Flaeche. Sie steht, bis Atons erstes Vollbild ankommt — bei der
Seiten-Matrix waren das ueber zwei Minuten (ESP booten, WLAN, Konfigurationseintrag).

Diese Tests halten die drei Fallen fest, die beim Einrichten von Hand zugeschlagen haben.
Jede einzelne davon endete in einem `{"success":true}`, hinter dem nichts passiert war:

1. `psave` ZUSAMMEN mit dem Zustand in einer Anfrage wird von WLED still verworfen.
2. Ein eingefrorenes Segment wird nicht neu gezeichnet — `col` zu setzen aendert dort
   nur das JSON, nicht das Panel.
3. `cfg.def.ps` auf ein nicht existierendes Preset ist schlimmer als gar keins: WLED
   malt dann wieder die Vorgabe, und niemand sieht, woran es liegt. Genau so stand die
   Entry-Matrix da.
"""
import asyncio
import json
import types

import pytest

from panel import wled
from panel.wled import BOOT_PRESET_NAME, WledTransport, _boot_ps, _ist_schwarz


SCHWARZ = {"n": BOOT_PRESET_NAME, "on": True,
           "seg": [{"id": 0, "col": [[0, 0, 0], [0, 0, 0], [0, 0, 0]], "fx": 0}]}


@pytest.fixture(autouse=True)
def ohne_wartezeit(monkeypatch):
    """Die Pause zwischen den Kontrollversuchen ist am Geraet noetig, im Test nur laestig
    — sie machte die Datei von 0,3 auf 3,5 Sekunden langsam."""
    monkeypatch.setattr(wled, "VERIFY_PAUSE_S", 0)
    monkeypatch.setattr(wled, "SPEICHER_PAUSE_S", 0)


class Antwort:
    def __init__(self, nutzlast, status=200):
        self._nutzlast, self.status = nutzlast, status

    async def json(self, content_type=None):
        return self._nutzlast

    async def text(self):
        return json.dumps(self._nutzlast)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False


class Geraet:
    """Ein WLED-Geraet, das sich so verhaelt wie das echte — Fallen inklusive."""

    def __init__(self, presets=None, def_ps=0, psave_kombiniert_wirkt=False):
        self.presets = presets if presets is not None else {"0": {}}
        self.cfg = {"def": {"ps": def_ps, "on": True, "bri": 128}}
        self.zustand = {"seg": [{"id": 0, "frz": True,
                                 "col": [[255, 160, 0], [0, 0, 0], [0, 0, 0]]}]}
        #: Falle 1 nachgebildet: kombiniertes psave tut nichts, sofern nicht anders gewuenscht.
        self.psave_kombiniert_wirkt = psave_kombiniert_wirkt
        self.aufrufe: list[tuple[str, dict]] = []

    def get(self, url):
        self.aufrufe.append(("GET", {"url": url}))
        if url.endswith("/presets.json"):
            return Antwort(self.presets)
        if url.endswith("/json/cfg"):
            return Antwort(self.cfg)
        return Antwort(self.zustand)

    def post(self, url, data=None, headers=None):
        daten = json.loads(data)
        self.aufrufe.append(("POST", daten))
        if url.endswith("/json/cfg"):
            self.cfg["def"].update(daten.get("def", {}))
            return Antwort({"success": True})
        if "psave" in daten:
            hat_zustand = "seg" in daten or "on" in daten
            if hat_zustand and not self.psave_kombiniert_wirkt:
                # ⚠⚠ Falle 1: WLED meldet Erfolg und legt NICHTS an.
                return Antwort({"success": True})
            self.presets[str(daten["psave"])] = {
                "n": daten.get("n", ""), "on": self.zustand.get("on", True),
                "seg": [dict(s) for s in self.zustand["seg"]]}
            return Antwort({"success": True})
        # Zustandsschreibvorgang
        for gewuenscht in daten.get("seg", []):
            for seg in self.zustand["seg"]:
                if seg["id"] == gewuenscht.get("id", 0):
                    # ⚠⚠ Falle 2: auf einem eingefrorenen Segment schlaegt die Farbe zwar
                    # im JSON durch, das PANEL bleibt aber stehen. Der Test bildet das ab,
                    # indem er sich merkt, ob wirklich neu gezeichnet wurde.
                    seg.update(gewuenscht)
                    seg["gezeichnet"] = gewuenscht.get("frz") is False
        return Antwort({"success": True})


def transport(geraet, slot=1, segment=0):
    t = WledTransport.__new__(WledTransport)
    t.panel = types.SimpleNamespace(id="wohnzimmer", host="10.0.0.9",
                                    boot_preset_slot=slot, canvas_segment=segment)
    t.stat = types.SimpleNamespace(erreichbar=True, unerreichbar_seit=0.0,
                                   fehler=0, letzter_fehler="")
    t._letztes = ["irgendwas"]
    t._probe = False
    return t


def lauf(geraet, t):
    session = types.SimpleNamespace(get=geraet.get, post=geraet.post)
    return asyncio.run(t.bootbild_sichern(session))


# ── Der Normalfall: es fehlt, also wird es angelegt ──────────────────────────

def test_fehlendes_preset_wird_angelegt():
    g = Geraet()                      # keine Presets, def.ps = 0
    assert lauf(g, transport(g)) == "angelegt"
    assert g.presets["1"]["n"] == BOOT_PRESET_NAME
    assert g.presets["1"]["seg"][0]["col"][0] == [0, 0, 0]
    assert g.cfg["def"]["ps"] == 1, "ohne das zeigt der Bootweg weiter ins Leere"


def test_psave_geht_als_EIGENE_anfrage_raus():
    """⚠⚠ Falle 1. Genau daran ist die Handanlegung zweimal gescheitert."""
    g = Geraet()
    lauf(g, transport(g))
    psaves = [d for art, d in g.aufrufe if art == "POST" and "psave" in d]
    assert psaves, "es wurde ueberhaupt nicht gespeichert"
    for d in psaves:
        assert "seg" not in d, ("psave zusammen mit dem Zustand — WLED meldet Erfolg und "
                                "legt nichts an")


def test_schwarz_wird_mit_frz_false_geschrieben():
    """⚠⚠ Falle 2: sonst stimmt das JSON und das Panel leuchtet weiter orange."""
    g = Geraet()
    lauf(g, transport(g))
    zustaende = [d for art, d in g.aufrufe
                 if art == "POST" and "seg" in d and "psave" not in d]
    assert zustaende, "die Flaeche wurde nie auf Schwarz gestellt"
    assert all(s.get("frz") is False for d in zustaende for s in d["seg"])
    assert g.zustand["seg"][0]["gezeichnet"] is True


# ── Der haeufige Fall: alles in Ordnung, also NICHTS schreiben ───────────────

def test_bereits_richtig_schreibt_nicht_in_den_flash():
    """psave und cfg gehen in den Flash des ESP — bei jedem Einschalten waere das
    Verschleiss ohne Gegenwert."""
    g = Geraet(presets={"0": {}, "1": SCHWARZ}, def_ps=1)
    assert lauf(g, transport(g)) == "in Ordnung"
    assert [art for art, _ in g.aufrufe] == ["GET", "GET"], "es wurde geschrieben"


# ── Die Halbzustaende, die niemandem auffallen ──────────────────────────────

def test_bootweg_zeigt_auf_leeren_platz_wird_repariert():
    """★★ Genau so stand die Entry-Matrix: def.ps=1, aber Preset 1 gab es nicht.
    WLED malt dann wieder die Vorgabe — die Einstellung sieht richtig aus und wirkt nicht."""
    g = Geraet(presets={"0": {}}, def_ps=1)
    assert lauf(g, transport(g)) == "angelegt"
    assert g.presets["1"]["seg"][0]["col"][0] == [0, 0, 0]


def test_preset_da_aber_bootweg_zeigt_woanders_hin():
    g = Geraet(presets={"0": {}, "1": SCHWARZ}, def_ps=0)
    assert lauf(g, transport(g)) == "angelegt"
    assert g.cfg["def"]["ps"] == 1


def test_eigenes_preset_ist_nicht_schwarz_wird_richtiggestellt():
    bunt = {"n": BOOT_PRESET_NAME, "on": True,
            "seg": [{"id": 0, "col": [[12, 34, 56], [0, 0, 0], [0, 0, 0]]}]}
    g = Geraet(presets={"0": {}, "1": bunt}, def_ps=1)
    assert lauf(g, transport(g)) == "angelegt"
    assert g.presets["1"]["seg"][0]["col"][0] == [0, 0, 0]


# ── Fremdes bleibt fremd ────────────────────────────────────────────────────

def test_fremdes_preset_wird_NICHT_ueberschrieben():
    """Ein Preset ist Handarbeit. Es zu ueberschreiben waere stiller Datenverlust."""
    fremd = {"n": "Party", "on": True,
             "seg": [{"id": 0, "col": [[255, 0, 255], [0, 0, 0], [0, 0, 0]]}]}
    g = Geraet(presets={"0": {}, "1": fremd}, def_ps=0)
    lage = lauf(g, transport(g))
    assert "fremd belegt" in lage and "Party" in lage
    assert g.presets["1"] == fremd, "das Preset des Nutzers wurde angetastet"
    assert g.cfg["def"]["ps"] == 0, "auch der Bootweg darf dann nicht umgebogen werden"
    assert not [d for art, d in g.aufrufe if art == "POST"]


def test_fremde_playlist_gilt_auch_als_belegt():
    g = Geraet(presets={"0": {}, "2": {"n": "Runde", "playlist": {"ps": [1, 3]}}})
    assert "fremd belegt" in lauf(g, transport(g, slot=2))


# ── Wenn das Geraet nicht antwortet ─────────────────────────────────────────

def test_unerreichbares_geraet_meldet_nicht_geprueft_und_zaehlt_keinen_fehler():
    """Beim Einschalten braucht der ESP rund 20 s. Das ist kein Sendefehler, und die
    Pruefung muss es beim naechsten Takt einfach nochmal versuchen."""
    class Tot(Geraet):
        def get(self, url):
            raise OSError("Connect call failed")

    g = Tot()
    t = transport(g)
    lage = lauf(g, t)
    assert lage.startswith("nicht geprueft")
    assert t.stat.fehler == 0, "eine ausgefallene Nebenpruefung ist keine Stoerung"


# ── Was das echte Geraet antwortet, und die Attrappe zunaechst nicht ────────

def test_cfg_mit_def_null_laesst_die_pruefung_nicht_platzen():
    """⚠⚠ Am 17.08.2026 am echten Geraet aufgeflogen, im Attrappen-Test nicht:

    WLED antwortet auf ein `GET /json/cfg` unmittelbar NACH einem Konfigurations-
    schreibvorgang mit `{"def": null}`. Der Schluessel ist da, aber leer — `cfg.get(
    "def", {})` greift nur bei fehlendem Schluessel und lieferte None, der Zugriff
    darauf flog mit AttributeError aus der Pruefung heraus. Und zwar NACHDEM bereits
    geschrieben war: das Geraet blieb schwarz und die App bekam eine Ausnahme.
    """
    class NachSchreibenLeer(Geraet):
        def get(self, url):
            if url.endswith("/json/cfg") and any(a == "POST" for a, _ in self.aufrufe):
                return Antwort({"def": None})
            return super().get(url)

    g = NachSchreibenLeer()
    lage = lauf(g, transport(g))
    assert lage == "Bootweg zeigt nicht auf Preset 1", lage
    assert g.presets["1"]["seg"][0]["col"][0] == [0, 0, 0], "geschrieben wurde trotzdem"


def test_cfg_antwortet_mit_nacktem_null():
    """⚠⚠ Der zweite Anlauf desselben Fehlers, ebenfalls nur am Geraet sichtbar.

    Nach dem Konfigurationsschreibvorgang liefert WLED nicht `{"def": null}`, sondern
    ein nacktes `null` — HTTP 200, gueltiges JSON, aber kein Woerterbuch. Erst gegen
    `cfg["def"]` abgesichert zu haben reichte deshalb nicht; die Umwandlung gehoert in
    `_get`, an die EINE Stelle, an der gelesen wird.
    """
    class LiefertNull(Geraet):
        def get(self, url):
            if url.endswith("/json/cfg") and any(a == "POST" for a, _ in self.aufrufe):
                return Antwort(None)
            return super().get(url)

    g = LiefertNull()
    lage = lauf(g, transport(g))          # darf nicht platzen
    assert lage == "Bootweg zeigt nicht auf Preset 1", lage


def test_get_macht_aus_jeder_antwort_ein_woerterbuch():
    for nutzlast in (None, [], "text", 7):
        g = Geraet()
        g.get = lambda url, _n=nutzlast: Antwort(_n)
        t = transport(g)
        session = types.SimpleNamespace(get=g.get, post=g.post)
        assert asyncio.run(t._get(session, "/json/cfg")) == {}


def test_kontrolle_wartet_auf_den_flash_statt_falsch_alarm_zu_schlagen():
    """⚠⚠ Am 17.08.2026 am Geraet: WLED legt `presets.json` im Flash ab und beantwortet
    ein SOFORTIGES GET noch aus dem alten Stand. Die Kontrolle meldete deshalb
    „liess sich nicht anlegen", waehrend das Geraet Sekundenbruchteile spaeter richtig
    dastand.

    Der Falschalarm ist nicht bloss haesslich: er wuerde bei JEDEM Einschalten neu
    schreiben und den Flash verschleissen, obwohl alles in Ordnung ist.
    """
    class Traege(Geraet):
        """Zeigt das frisch gespeicherte Preset erst beim dritten Nachsehen."""
        verzoegerung = 2

        def get(self, url):
            if url.endswith("/presets.json") and self.verzoegerung:
                self.verzoegerung -= 1
                self.aufrufe.append(("GET", {"url": url}))
                return Antwort({"0": {}})          # noch der alte Stand
            return super().get(url)

    g = Traege()
    assert lauf(g, transport(g)) == "angelegt"


def test_kontrolle_gibt_irgendwann_auf():
    """Ewig nachsehen waere genauso falsch — irgendwann muss es eine Meldung geben."""
    class NieFertig(Geraet):
        def get(self, url):
            if url.endswith("/presets.json") and any(a == "POST" for a, _ in self.aufrufe):
                return Antwort({"0": {}})
            return super().get(url)

    g = NieFertig()
    assert lauf(g, transport(g)) == "Preset 1 liess sich nicht anlegen"


def test_abriss_beim_schreiben_fuehrt_zu_erneutem_versuch():
    """Faellt das Geraet mitten im Schreiben aus, darf die Ausnahme nicht in den
    Sendetakt durchschlagen — und beim naechsten Mal wird es nochmal versucht."""
    class Wackelig(Geraet):
        def post(self, url, data=None, headers=None):
            raise OSError("Server disconnected")

    g = Wackelig()
    t = transport(g)
    lage = lauf(g, t)
    assert lage.startswith("nicht geprueft")
    assert t._letztes is None, "nach einem Abriss muss ein Vollbild folgen"


def test_nach_dem_anlegen_folgt_ein_vollbild():
    """`_setze_schwarz` loescht die Flaeche. Ohne `_letztes = None` schickt der
    Transport nur die Unterschiede — und die Matrix bliebe schwarz."""
    g = Geraet()
    t = transport(g)
    assert t._letztes is not None
    lauf(g, t)
    assert t._letztes is None


# ── Die Hilfsfunktion ───────────────────────────────────────────────────────

@pytest.mark.parametrize("cfg, erwartet", [
    ({"def": {"ps": 1}}, 1),
    ({"def": {"ps": "1"}}, 1),      # WLED antwortet mal als Zahl, mal als Zeichenkette
    ({"def": None}, None),          # ⚠ genau der Fall vom Geraet
    ({}, None),
    ({"def": {}}, None),
    ({"def": {"ps": 0}}, 0),        # 0 = kein Boot-Preset
])
def test_boot_ps(cfg, erwartet):
    assert _boot_ps(cfg) == erwartet

@pytest.mark.parametrize("preset, erwartet", [
    (SCHWARZ, True),
    ({}, False),
    ({"n": "x"}, False),
    ({"seg": [{"id": 0, "col": [[0, 0, 0]]}]}, True),
    ({"seg": [{"id": 0, "col": [[1, 0, 0]]}]}, False),
    ({"seg": [{"id": 1, "col": [[0, 0, 0]]}]}, False),        # falsches Segment
    ({"seg": [{"id": 0, "col": [[0, 0, 0, 0]]}]}, True),      # RGBW
])
def test_ist_schwarz(preset, erwartet):
    assert _ist_schwarz(preset, 0) is erwartet


def test_ist_schwarz_achtet_auf_das_bildsegment():
    p = {"seg": [{"id": 0, "col": [[255, 0, 0]]}, {"id": 2, "col": [[0, 0, 0]]}]}
    assert _ist_schwarz(p, 2) is True
    assert _ist_schwarz(p, 0) is False


# ── Sichtbarkeit: die Pruefung schweigt im Gutfall ──────────────────────────

def test_lage_landet_in_der_statistik_und_damit_im_sensor():
    """★ Eine stille Pruefung haelt man spaeter fuer nie gelaufen. Deshalb muss ihr
    Ergebnis irgendwo stehen — `Statistik.bootbild` geht ueber `/api/status` in einen
    Diagnose-Sensor."""
    from panel.wled import Statistik
    assert Statistik().bootbild == "", "leer heisst: noch nicht geprueft"


def test_abgeschaltet_wartet_nicht_auf_eine_pruefung_die_nie_kommt():
    """⚠ Mit `boot_preset: false` laeuft die Pruefung nie. Stuende der Sensor dann fuer
    immer auf „noch nicht geprueft", waere das eine Anzeige, die auf etwas warten laesst,
    das gar nicht kommt."""
    from panel.display import bootbild_start

    def cfg(boot, dry):
        return types.SimpleNamespace(boot_preset=boot, dry_run=dry)

    assert bootbild_start(cfg(True, False)) == (True, "")
    assert bootbild_start(cfg(False, False)) == (False, "abgeschaltet")
    assert bootbild_start(cfg(True, True)) == (False, "Probelauf")
    assert bootbild_start(cfg(False, True)) == (False, "Probelauf")


def test_display_uebernimmt_die_anfangslage_wirklich():
    """★ Der vorige Test prueft nur die Funktion. Dass `Display.__init__` sie auch
    benutzt, ist eine eigene Frage — sonst prueft man eine Regel, die niemand anwendet."""
    import inspect
    from panel import display as d
    quelle = inspect.getsource(d.Display.__init__)
    assert "bootbild_start(panel)" in quelle
