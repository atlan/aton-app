"""Oberflaeche in HAs Seitenleiste (Ingress).

Der Grund, warum das eine App ist und keine Integration: hier laesst sich **sehen**, was
die Matrix zeigt, ohne im Wohnzimmer zu stehen. Der Bildspeicher wird als PNG ausgeliefert,
vergroessert und mit sichtbarem Pixelraster — damit ist auch am Schreibtisch nachpruefbar,
ob eine Kachel an der richtigen Stelle steht.

Alle Pfade sind **relativ**, sonst bricht Ingress (die Seite laeuft unter
/api/hassio_ingress/<token>/).
"""
from __future__ import annotations

import io
import logging
import os

from aiohttp import web

from .const import INGRESS_PORT, WWW_DIR, anzeige_pfad, version
from .konfigurator import KonfiguratorAPI, _stand
from .render import vergroessern

_LOG = logging.getLogger(__name__)


class WebUI:
    def __init__(self, app_state):
        self.app_state = app_state

    def _display(self, request) -> object:
        pid = request.match_info["panel"]
        display = self.app_state.displays.get(pid)
        if display is None:
            raise web.HTTPNotFound(text=f"Anzeige '{pid}' gibt es nicht")
        return display

    # ------------------------------------------------------------------
    async def index(self, request):
        """Die Seite ausliefern — mit einer Kennung an den Verweisen auf Skript und Stil.

        ★ Ohne diese Kennung sieht man neue Oberflaeche schlicht nicht: der Browser haelt
        `static/konfigurator.js` fuer unveraendert (die Auslieferung schickte kein
        `Cache-Control`, also faellt er auf seine eigene Faustregel zurueck) und laedt die
        alte Fassung aus dem Zwischenspeicher — auch nach einem Neuladen der Seite.
        Gemessen: der Server lieferte den neuen Stand aus, im Browser stand der alte.

        Die Kennung ist die Aenderungszeit der Datei. Damit bekommt jede neue Fassung eine
        neue Adresse, und der Zwischenspeicher greift wieder, sobald sich nichts aendert.
        """
        pfad = os.path.join(WWW_DIR, "index.html")
        with open(pfad, encoding="utf-8") as fh:
            text = fh.read()
        # ★★ Die Kennung steckt im DATEINAMEN, nicht im Query-Teil.
        # `konfigurator.js?v=123` sieht fuer einen Service Worker aus wie
        # `konfigurator.js` — Workbox & Co. duerfen den Query beim Nachschlagen
        # ignorieren und antworten dann mit einer alten Kopie, egal welche Kennung
        # dranhaengt. Am 06.08. genau so erlebt: der Server lieferte nachweislich die
        # neue Datei aus, der Browser fuehrte stundenlang die alte aus, und jede
        # Massnahme auf Serverseite blieb wirkungslos.
        # Ein anderer PFAD ist dagegen ein anderer Eintrag — daran kommt kein
        # Zwischenspeicher vorbei.
        for datei in ("konfigurator.js", "konfigurator.css", "symboleditor.js"):
            voll = os.path.join(WWW_DIR, datei)
            marke = int(os.path.getmtime(voll)) if os.path.exists(voll) else 0
            stamm, endung = os.path.splitext(datei)
            text = text.replace(f"static/{datei}", f"static/{stamm}.{marke}{endung}")
        # ★ Den Stand direkt in die Seite schreiben, statt ihn spaeter aus dem
        # Konfigurator zu nehmen: der setzt ihn erst, wenn SEIN Reiter geladen hat — wer
        # auf dem Betriebs-Reiter bleibt, haette den Vergleich also nie bekommen. Genau
        # der, der lange auf einer Seite steht, braucht ihn am dringendsten.
        stand = _stand()
        text = text.replace("{{STAND}}", stand)
        # ⚠ Jede ausgelieferte Seite ins Protokoll. Das sind wenige Zeilen am Tag, aber
        # der einzige Weg, „mein Browser holt die Seite gar nicht neu" von „die App
        # liefert Altes aus" zu unterscheiden — genau daran haben wir am 06.08. eine
        # Stunde verloren. Wer neu laedt und KEINE Zeile erzeugt, bekommt seine Seite
        # aus einem Zwischenspeicher.
        _LOG.info("Seite ausgeliefert (Stand %s) an %s", stand,
                  request.headers.get("X-Forwarded-For") or (request.remote or "?"))
        return web.Response(text=text, content_type="text/html",
                            headers={"Cache-Control": "no-store"})

    async def statisch_mit_kennung(self, request):
        """`konfigurator.<kennung>.js` auf `konfigurator.js` zurueckfuehren.

        Die Kennung dient nur dazu, jeder Fassung einen EIGENEN Pfad zu geben; auf der
        Platte liegt weiterhin eine Datei ohne sie. Passt der Name nicht auf dieses
        Muster, wird ganz normal die gleichnamige Datei geliefert — die uebrigen
        Oberflaechendateien (Symbole, Schriftproben) sollen unveraendert funktionieren.
        """
        name = request.match_info["name"]
        stamm, endung = os.path.splitext(name)
        teile = stamm.rsplit(".", 1)
        if len(teile) == 2 and teile[1].isdigit():
            name = teile[0] + endung
        voll = os.path.normpath(os.path.join(WWW_DIR, name))
        # ⚠ Pfadausbruch verhindern: `name` kommt aus der Adresse.
        if not voll.startswith(os.path.realpath(WWW_DIR)) or not os.path.isfile(voll):
            raise web.HTTPNotFound()
        return web.FileResponse(voll)

    async def stand(self, request):
        """Nur der Stand — winzig, damit die Oberflaeche ihn HAEUFIG und auf JEDEM Reiter
        holen kann.

        ⚠ Er hing vorher an `/api/panels`, und dessen Abruf bricht ab, sobald der
        Betriebs-Reiter nicht sichtbar ist. Wer im Konfigurator arbeitet — also genau
        dort, wo eine alte Fassung am meisten anrichtet — bekam die Warnung nie.
        """
        return web.json_response({"stand": _stand()})

    async def panels(self, request):
        daten = []
        for pid, d in self.app_state.displays.items():
            stat = d.transport.stat
            erg = d.letztes_ergebnis
            daten.append({
                "id": pid,
                "name": d.cfg.name,
                "host": d.cfg.host,
                "size": [d.cfg.width, d.cfg.height],
                "an": d.freigegeben(),
                "probelauf": d.cfg.dry_run,
                "helligkeit": d.helligkeit(),
                "eigene_helligkeit": not d.cfg.brightness_entity,
                # Womit der Schalter arbeitet — die Oberflaeche zeigt es im Hinweis an,
                # damit man nicht raetselt, was ein Klick eigentlich ausloest.
                "schaltweg": (d.cfg.gate_script or d.cfg.gate_entity
                              or d.cfg.gate_fallback or ""),
                "schaltbar": bool(d.cfg.gate_script or d.cfg.gate_entity
                                  or d.cfg.gate_fallback),
                "intervall": d.cfg.interval,
                "erreichbar": stat.erreichbar,
                "frames": stat.frames,
                "vollbilder": stat.vollbilder,
                "pixel": stat.letzte_pixel,
                "bytes": stat.letzte_bytes,
                "fehler": stat.fehler,
                "letzter_fehler": stat.letzter_fehler,
                # Erreichbarkeit als ZUSTAND (siehe `Statistik.unerreichbar_seit`):
                # eine Matrix, die eine Nacht lang stromlos war, ist ein Sachverhalt
                # und keine 5888 Vorfaelle.
                "unerreichbar_seit": stat.unerreichbar_seit,
                "sendepause": d.sendepause,
                "letzter_lauf": d.letzter_lauf,
                "render_fehler": erg.fehler if erg else [],
                "notiz": d.aktive_notiz(),
                "gruppen": [
                    {
                        "id": g.id,
                        "name": g.name,
                        "region": list(g.region),
                        "screens": [s.name for s in g.screens],
                        "vorwahl": d.vorwahl.get(g.id) or "Automatik",
                        "aktiv": (erg.aktive_screens.get(g.id) if erg else None),
                    }
                    for g in d.cfg.groups
                ],
            })
        return web.json_response({"panels": daten,
                                  "quelle": anzeige_pfad(self.app_state.cfg.quelle),
                                  # Die Begleit-Integration traegt das als `sw_version`
                                  # ins Geraet ein — so steht auf der Geraetekarte,
                                  # welcher Stand der App die Anzeige gerade bedient.
                                  "version": version(),
                                  # ★ Der Stand, den der Server GERADE ausliefert. Die
                                  # Oberflaeche vergleicht ihn mit dem, mit dem sie selbst
                                  # geladen wurde — weicht er ab, laeuft im Browser eine
                                  # alte Fassung, und genau das sieht man ihr sonst nicht
                                  # an. Zweimal an einem Abend gesucht, beim zweiten Mal
                                  # ueber eine Stunde.
                                  "stand": _stand(),
                                  # Leer, solange alles gut ist. Steht hier etwas, ist die
                                  # Liste oben aus GUTEM Grund leer — ohne diese Angabe
                                  # saehe die Betriebsansicht einfach nur kaputt aus.
                                  "ladefehler": self.app_state.ladefehler})

    async def vorschau(self, request):
        """Aktuelles Bild als PNG — `?zoom=6` vergroessert, `?raster=1` zeigt das Pixelgitter."""
        d = self._display(request)
        bild = d.vorschaubild()

        zoom = max(1, min(20, int(request.query.get("zoom", 6))))
        gross, _ = vergroessern(bild, zoom, d.cfg.led_pitch,
                                gitter=request.query.get("raster") == "1")
        puffer = io.BytesIO()
        gross.save(puffer, "PNG")
        return web.Response(body=puffer.getvalue(), content_type="image/png",
                            headers={"Cache-Control": "no-store"})

    async def waehle(self, request):
        d = self._display(request)
        daten = await request.json()
        d.waehle(str(daten["gruppe"]), str(daten["wert"]))
        return web.json_response({"ok": True})

    async def vollbild(self, request):
        self._display(request).vollbild_erzwingen()
        return web.json_response({"ok": True})

    async def setze_helligkeit(self, request):
        d = self._display(request)
        daten = await request.json()
        # ⚠ Den gesetzten Wert MELDEN, nicht zurueckholen: `helligkeit()` liest aus HAs
        # Zustandsspiegel, und der hinkt direkt nach dem Setzen noch hinterher. Die
        # Antwort behauptete dadurch den alten Wert.
        neu = await d.setze_helligkeit(daten["wert"])
        if neu is None:
            return web.json_response({"ok": False, "helligkeit": d.helligkeit()},
                                     status=502)
        return web.json_response({"ok": True, "helligkeit": neu})

    async def schalten(self, request):
        d = self._display(request)
        daten = await request.json() if request.can_read_body else {}
        an = bool(daten.get("an", True))
        ok, was = await d.schalte(an)
        # `skript` sagt der Oberflaeche, wie lange sie auf den Zustandswechsel warten
        # darf: ein direkt geschaltetes Tor meldet sich in Sekundenbruchteilen, ein
        # Schaltskript braucht Booten, Konfigurationseintrag und Vollbild — gut eine
        # halbe Minute. Ohne diese Angabe muesste die Oberflaeche im Meldungstext
        # herumraten.
        return web.json_response({"ok": ok, "was": was, "skript": bool(d.cfg.gate_script)},
                                 status=200 if ok else 502)

    async def notiz(self, request):
        d = self._display(request)
        daten = await request.json()
        nid = d.notiz_setzen(daten)
        return web.json_response({"ok": True, "id": nid})

    async def notiz_loeschen(self, request):
        d = self._display(request)
        daten = await request.json() if request.can_read_body else {}
        d.notiz_loeschen(daten.get("id"), daten.get("channel"))
        return web.json_response({"ok": True})

    # ------------------------------------------------------------------
    def app(self) -> web.Application:
        anwendung = web.Application()
        anwendung.add_routes([
            web.get("/", self.index),
            web.get("/api/panels", self.panels),
            web.get("/api/stand", self.stand),
            web.get("/api/panel/{panel}/preview.png", self.vorschau),
            web.post("/api/panel/{panel}/screen", self.waehle),
            web.post("/api/panel/{panel}/vollbild", self.vollbild),
            web.post("/api/panel/{panel}/helligkeit", self.setze_helligkeit),
            web.post("/api/panel/{panel}/schalten", self.schalten),
            web.post("/api/panel/{panel}/notify", self.notiz),
            web.post("/api/panel/{panel}/notify_clear", self.notiz_loeschen),
        ])
        anwendung.add_routes(KonfiguratorAPI(self.app_state).routen())
        # ⚠ MUSS vor `add_static` stehen: die statische Route wuerde
        # `konfigurator.1785971601.js` sonst als eigene, nicht vorhandene Datei
        # behandeln und mit 404 antworten.
        anwendung.router.add_get("/static/{name}", self.statisch_mit_kennung)
        anwendung.router.add_static("/static/", WWW_DIR)
        anwendung.on_response_prepare.append(_nicht_raten)
        return anwendung



async def _nicht_raten(request, antwort) -> None:
    """Dem Browser das Raten abgewoehnen.

    Ohne `Cache-Control` entscheidet er nach eigener Faustregel, wie lange etwas frisch
    ist. `no-cache` heisst nicht "nicht speichern", sondern "vor dem Benutzen
    nachfragen" — die Antwort ist dann meist ein 304, kostet also fast nichts.
    """
    if request.path.startswith("/static/") and "Cache-Control" not in antwort.headers:
        antwort.headers["Cache-Control"] = "no-cache"


async def starte(app_state) -> web.AppRunner:
    ui = WebUI(app_state)
    runner = web.AppRunner(ui.app())
    await runner.setup()
    seite = web.TCPSite(runner, "0.0.0.0", INGRESS_PORT)
    await seite.start()
    _LOG.info("Oberflaeche laeuft auf Port %d", INGRESS_PORT)
    return runner
