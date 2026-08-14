"""Die Schnittstelle des Konfigurators.

Getrennt von `web.py`, weil das etwas anderes ist: `web.py` zeigt den Betrieb, hier wird
die Beschreibung bearbeitet. Beides teilt sich nur den Webserver.

Der wichtigste Endpunkt ist `/api/config/preview`: er rendert einen **Entwurf**, ohne ihn
zu speichern. Man sieht also, was eine Änderung bewirkt, bevor sie in der Datei steht — bei
einer Anzeige, die man sonst nur im Wohnzimmer beurteilen kann, ist das der Unterschied
zwischen Arbeiten und Raten.
"""
from __future__ import annotations

import io
import logging
import os

from aiohttp import web
from PIL import Image

from . import configfile, migration, plugin, schema
from .config import ConfigError, pruefe
from .const import UNAVAILABLE_STATES, WWW_DIR, anzeige_pfad, version
from .fonts import SCHRIFT_VORGABEN
from .render import Renderer, vergroessern

_LOG = logging.getLogger(__name__)


class KonfiguratorAPI:
    def __init__(self, app_state):
        self.s = app_state

    # ------------------------------------------------------------------
    def _sprache(self, request) -> str:
        return self.s.katalog.waehle(
            request.query.get("lang") or request.headers.get("Accept-Language"))

    async def schema_holen(self, request):
        sprache = self._sprache(request)
        return web.json_response({
            "stand": _stand(),
            "symbolmarke": _symbolmarke(self.s.icons),
            "sprache": sprache,
            "sprachen": self.s.katalog.sprachen,
            "schema": schema.als_dict(self.s.katalog, sprache,
                                      plugin.registry.als_dict(), plugin.registry.fehler),
            "texte": self.s.katalog.alle(sprache),
        })

    async def config_holen(self, request):
        pfad = self.s.pfad
        daten, mtime, text = configfile.lese(pfad)
        # Veraltete Namen kommen gar nicht erst im Browser an. Sonst zeigt das Formular
        # die Felder des neuen Typs und das Datenmodell traegt den alten Namen weiter —
        # und beim Speichern stuende der alte wieder in der Datei.
        # ⚠ Nur die Kopie im Speicher. Geschrieben wird ausschliesslich beim Speichern.
        umbenannt = migration.migriere(daten)
        return web.json_response({
            "pfad": anzeige_pfad(pfad),
            "mtime": mtime,
            "yaml": text,
            "daten": _rein(daten),
            "umbenannt": umbenannt,
        })

    async def pruefen(self, request):
        entwurf = (await request.json()).get("daten")
        try:
            cfg = pruefe(entwurf, "(Entwurf)")
        except ConfigError as e:
            return web.json_response({"ok": False, "pfad": e.pfad, "meldung": str(e)})
        return web.json_response({
            "ok": True,
            "panels": [{"id": p.id, "name": p.name, "size": [p.width, p.height],
                        "widgets": len(p.widgets),
                        "gruppen": [{"id": g.id, "name": g.name,
                                     "screens": [s.name for s in g.screens]}
                                    for g in p.groups]}
                       for p in cfg.panels],
        })

    async def vorschau(self, request):
        """Einen Entwurf rendern, ohne ihn zu speichern."""
        daten = await request.json()
        entwurf = daten.get("daten")
        panel_id = daten.get("panel")
        vorwahl = daten.get("vorwahl") or {}
        # ★ Zwei Vorwahlen, weil es zwei Ebenen sind: `vorwahl` waehlt den Screen einer
        # Gruppe, `seiten_vorwahl` die Seite INNERHALB des Screens. Fehlt die zweite,
        # entscheidet die Uhr — und die Auswahl im Baum bliebe wirkungslos.
        seiten_vorwahl = daten.get("seiten") or {}
        zoom = max(1, min(20, int(daten.get("zoom", 6))))

        try:
            cfg = pruefe(entwurf, "(Entwurf)")
        except ConfigError as e:
            return web.json_response({"ok": False, "pfad": e.pfad, "meldung": str(e)},
                                     status=400)

        panel = next((p for p in cfg.panels if p.id == panel_id), None) or cfg.panels[0]
        renderer = Renderer(panel, self.s.ha, self.s.fonts, self.s.icons,
                            getattr(self.s, 'verlauf', None))
        ergebnis = renderer.frame(vorwahl, daten.get("notiz"), seiten_vorwahl)

        # ⚠ Vergroessern, Gitter und Punktdarstellung liegen in EINER Funktion, die auch
        # der Betriebs-Reiter benutzt — sonst sehen dieselben Daten an zwei Stellen
        # unterschiedlich aus und man sucht den Unterschied im Renderer statt in der
        # Abfrage. Der tatsaechlich benutzte Zoom kommt zurueck: bei gesetztem
        # `led_pitch` weicht er vom angeforderten ab, und die Oberflaeche rechnet damit
        # Klick- und Ziehpositionen um.
        bild, zoom = vergroessern(ergebnis.bild, zoom, panel.led_pitch,
                                  gitter=bool(daten.get("raster", True)))
        puffer = io.BytesIO()
        bild.save(puffer, "PNG")
        import base64
        pi = next(i for i, p in enumerate(cfg.panels) if p.id == panel.id)
        return web.json_response({
            "ok": True,
            "png": "data:image/png;base64," + base64.b64encode(puffer.getvalue()).decode(),
            "zoom": zoom,
            "groesse": [panel.width, panel.height],
            "aktive_screens": ergebnis.aktive_screens,
            "fehler": ergebnis.fehler,
            "kacheln": _kacheln(cfg, panel, pi, ergebnis.aktive_screens,
                                ergebnis.aktive_seiten),
            "aktive_seiten": ergebnis.aktive_seiten,
        })

    async def speichern(self, request):
        daten = await request.json()
        entwurf = daten.get("daten")
        # Veraltete Namen werden hier umgeschrieben, nicht nur geduldet: der Konfigurator
        # schreibt die Datei ohnehin neu, und ein alter Name, der bleibt, weil ihn niemand
        # anfasst, faellt spaeter als Fehler auf (Formular zeigt den neuen Typ, Datei sagt
        # den alten). Nach `config_holen` ist der Entwurf meist schon migriert — nicht aber
        # bei einem Browser, der die Seite seit einer aelteren Fassung offen hat.
        umbenannt = migration.migriere(entwurf)
        try:
            pruefe(entwurf, "(Entwurf)")
        except ConfigError as e:
            return web.json_response({"ok": False, "pfad": e.pfad, "meldung": str(e)},
                                     status=400)

        # In die vorhandene Struktur einarbeiten — so ueberleben die Kommentare.
        vorhanden, mtime, _ = configfile.lese(self.s.pfad)
        # ★ Auch die vorhandene Struktur, und zwar VOR dem Verschmelzen: sonst sieht die
        # Verschmelzung `seiten` (Datei) gegen `pages` (Entwurf), loescht das eine und
        # haengt das andere ans Ende — mitsamt Kommentarverlust an dieser Stelle.
        # Positionstreu umbenannt bleibt beides an seinem Platz.
        # ⚠ Und DIESE Liste ist die interessante: der Entwurf kam meist schon migriert aus
        # `config_holen` zurueck, oben faellt also nichts mehr an. Was sich wirklich in der
        # DATEI aendert, steht hier.
        umbenannt = sorted(set(umbenannt) | set(migration.migriere(vorhanden)))
        verschmolzen = configfile.verschmelze(vorhanden, entwurf)
        try:
            sicherung = configfile.schreibe(self.s.pfad, verschmolzen,
                                            daten.get("mtime") or mtime)
        except configfile.SchreibFehler as e:
            return web.json_response({"ok": False, "meldung": str(e)}, status=409)
        configfile.sicherungen_aufraeumen(self.s.pfad)

        neu_mtime = os.path.getmtime(self.s.pfad)
        geladen = await self.s.neu_laden()
        if umbenannt:
            _LOG.info("Beim Speichern umgeschrieben: %s", "; ".join(umbenannt))
        return web.json_response({"ok": True, "mtime": neu_mtime,
                                  "sicherung": os.path.basename(sicherung),
                                  "umbenannt": umbenannt,
                                  "neu_geladen": geladen})

    async def neu_laden(self, request):
        geladen = await self.s.neu_laden()
        return web.json_response({"ok": geladen})

    # -- Nachschlagen fuer die Formulare ---------------------------------
    async def entitaeten(self, request):
        """Entitaeten aus dem Zustandsspiegel — damit niemand IDs abtippen muss."""
        suche = (request.query.get("q") or "").lower()
        grenze = int(request.query.get("limit", 40))
        treffer = []
        for eid in sorted(self.s.ha._states):
            if suche and suche not in eid.lower():
                continue
            zustand = self.s.ha.state(eid)
            treffer.append({"id": eid, "zustand": zustand,
                            "leer": zustand in UNAVAILABLE_STATES})
            if len(treffer) >= grenze:
                break
        return web.json_response({"entitaeten": treffer, "gesamt": self.s.ha.anzahl})

    async def symbole(self, request):
        return web.json_response({"symbole": self.s.icons.namen()})

    async def symbol_bild(self, request):
        name = request.match_info["name"]
        try:
            symbol = self.s.icons.get(name)
        except KeyError:
            raise web.HTTPNotFound(text=f"Symbol '{name}' gibt es nicht")
        zoom = max(1, min(16, int(request.query.get("zoom", 6))))
        gross = symbol.resize((symbol.width * zoom, symbol.height * zoom), Image.NEAREST)
        puffer = io.BytesIO()
        gross.save(puffer, "PNG")
        return web.Response(body=puffer.getvalue(), content_type="image/png")

    # -- Symbol-Editor ---------------------------------------------------
    async def symbol_punkte(self, request):
        """Ein Symbol als Pixelliste — die Grundlage des Editors.

        Auch mitgelieferte Symbole lassen sich so oeffnen. Speichert man sie danach unter
        demselben Namen, entsteht eine eigene Datei, die das mitgelieferte ueberdeckt —
        genau der dokumentierte Weg, eines zu ersetzen.
        """
        name = request.match_info["name"]
        try:
            bild = self.s.icons.get(name).convert("RGBA")
        except KeyError:
            raise web.HTTPNotFound(text=f"Symbol '{name}' gibt es nicht")
        punkte = ["%02x%02x%02x%02x" % p for p in bild.getdata()]
        return web.json_response({
            "name": name, "breite": bild.width, "hoehe": bild.height,
            "punkte": punkte, "eigen": self.s.icons.ist_eigen(name),
        })

    async def symbol_speichern(self, request):
        daten = await request.json()
        name = (daten.get("name") or "").strip()
        breite = int(daten.get("breite", 8))
        hoehe = int(daten.get("hoehe", 8))
        punkte = daten.get("punkte") or []

        if not 1 <= breite <= 64 or not 1 <= hoehe <= 64:
            return web.json_response({"ok": False, "meldung": "Groesse 1..64"}, status=400)
        if len(punkte) != breite * hoehe:
            return web.json_response(
                {"ok": False,
                 "meldung": f"{len(punkte)} Punkte, erwartet {breite * hoehe}"}, status=400)

        bild = Image.new("RGBA", (breite, hoehe))
        try:
            bild.putdata([_rgba(p) for p in punkte])
        except ValueError as e:
            return web.json_response({"ok": False, "meldung": str(e)}, status=400)

        try:
            self.s.icons.speichere(name, bild)
        except ValueError as e:
            return web.json_response({"ok": False, "meldung": str(e)}, status=400)
        except OSError as e:
            return web.json_response({"ok": False, "meldung": f"Schreiben: {e}"}, status=500)
        return web.json_response({"ok": True, "name": name,
                                  "symbole": self.s.icons.namen()})

    async def symbol_loeschen(self, request):
        name = request.match_info["name"]
        if not self.s.icons.loesche(name):
            return web.json_response(
                {"ok": False, "meldung": "Nur eigene Symbole lassen sich loeschen"},
                status=400)
        return web.json_response({"ok": True, "symbole": self.s.icons.namen()})

    async def schriften(self, request):
        """Namen — und dazu, was fuer jede Schrift OHNE eigenen Eintrag gilt.

        Ohne diese Vorgaben liesse sich im Konfigurator nicht unterscheiden, ob eine
        Schrift Grossschrift erzwingt, weil es so eingebaut ist, oder weil jemand es
        eingetragen hat. Genau das will man aber sehen, bevor man daran dreht.
        """
        eingebaut = {}
        for name in self.s.fonts.namen():
            stamm = name.partition("@")[0]
            regeln = SCHRIFT_VORGABEN.get(stamm)
            if regeln:
                eingebaut[name] = {"uppercase": bool(regeln.get("uppercase")),
                                   "transliterate": bool(regeln.get("transliterate"))}
        return web.json_response({"schriften": self.s.fonts.namen(),
                                  "eingebaut": eingebaut})

    # ------------------------------------------------------------------
    def routen(self) -> list:
        return [
            web.get("/api/schema", self.schema_holen),
            web.get("/api/config", self.config_holen),
            web.post("/api/config/validate", self.pruefen),
            web.post("/api/config/preview", self.vorschau),
            web.post("/api/config", self.speichern),
            web.post("/api/reload", self.neu_laden),
            web.get("/api/entities", self.entitaeten),
            web.get("/api/icons", self.symbole),
            web.get("/api/icons/{name}.png", self.symbol_bild),
            web.get("/api/icons/{name}/punkte", self.symbol_punkte),
            web.post("/api/icons", self.symbol_speichern),
            web.delete("/api/icons/{name}", self.symbol_loeschen),
            web.get("/api/fonts", self.schriften),
        ]


def _rgba(p: str) -> tuple[int, int, int, int]:
    """`rrggbbaa` (oder `rrggbb`, dann deckend) in ein Tupel."""
    p = str(p).lstrip("#")
    if len(p) == 6:
        p += "ff"
    if len(p) != 8:
        raise ValueError(f"Punkt '{p}': erwartet rrggbb oder rrggbbaa")
    try:
        return tuple(int(p[i:i + 2], 16) for i in (0, 2, 4, 6))
    except ValueError:
        raise ValueError(f"Punkt '{p}': keine Hexzahl") from None


def _symbolmarke(icons) -> int:
    """Neueste Aenderungszeit unter den eigenen Symbolen.

    ★ Damit bekommt die Oberflaeche eine Kennung fuer die Symbolbilder, die auch dann
    stimmt, wenn jemand ANDERSWO gezeichnet hat — im zweiten Browserfenster, in der
    vorigen Sitzung, direkt im Dateisystem. Ein Zaehler, der nur beim eigenen Speichern
    hochlaeuft, wuerde genau diese Faelle verpassen.
    """
    marke = 0
    for name in icons.namen():
        pfad = icons.datei(name)
        if pfad:
            try:
                marke = max(marke, int(os.path.getmtime(pfad)))
            except OSError:
                pass
    return marke


def _stand() -> str:
    """Version der App plus Aenderungszeit der Oberflaeche.

    ★ Zweimal hintereinander ist es passiert, dass der Server laengst den neuen Stand
    auslieferte und im Browser der alte stand. Das ist von aussen nicht zu sehen — also
    schreibt die Oberflaeche hin, welchen Stand sie SELBST hat. Passt er nicht zum
    erwarteten, ist die Sache in einer Sekunde geklaert statt in zwanzig Minuten.
    """
    # ⚠ Ueber ALLE Oberflaechendateien, nicht nur ueber `konfigurator.js`. Genau daran
    # ist der Stempel schon einmal gescheitert: eine Aenderung an `symboleditor.js` liess
    # ihn unveraendert — das Werkzeug zeigte also gerade das nicht an, wofuer es da ist.
    marke = 0
    for datei in sorted(os.listdir(WWW_DIR)) if os.path.isdir(WWW_DIR) else []:
        if datei.endswith((".js", ".css", ".html")):
            marke = max(marke, int(os.path.getmtime(os.path.join(WWW_DIR, datei))))
    return f"{version()}\u00b7{marke}"


def _kacheln(cfg, panel, pi: int, aktiv: dict, seiten: dict | None = None) -> list[dict]:
    """Wo liegt welche Kachel — vom Server gerechnet, nicht von der Oberflaeche.

    ★ Die Lage einer Kachel ergibt sich aus `cell` und dem Raster oder aus `at`. Diese
    Rechnung ein zweites Mal in JavaScript zu fuehren waere eine sichere Quelle fuer
    Abweichungen: man klickt daneben, weil die Oberflaeche anders rechnet als der Renderer.
    Deshalb kommen die Rechtecke von dort, wo auch gezeichnet wird.
    """
    kacheln = []

    g = panel.grid

    def ausdehnung(w) -> tuple[int, int, int, int]:
        """Was die Kachel WIRKLICH einnimmt — Symbol und Textfeld zusammen.

        ⚠ `w.x/w.y/w.w/w.h` ist nur die Rasterzelle. Eine Kachel mit `text_at`/
        `text_width` ragt darueber hinaus — der Zaehlerstand etwa reicht bis in die
        Nachbarspalte. Wer das Rechteck aus der Zelle nimmt, markiert die halbe Kachel
        und trifft beim Anklicken daneben.
        """
        x0, y0 = w.x, w.y
        x1, y1 = w.x + w.w, w.y + w.h

        if w.type in ("tile", "icon") and w.icon:
            x1 = max(x1, w.x + g.icon_width)

        if w.text and w.type in ("tile", "text"):
            if w.type == "tile":
                tx = w.text_x if w.text_x is not None else w.x + g.icon_width + g.gap
                tw = w.text_w if w.text_w is not None else w.w - g.icon_width - g.gap
            else:
                tx = w.text_x if w.text_x is not None else w.x
                tw = w.text_w if w.text_w is not None else w.w
            ty = w.text_y if w.text_y is not None else w.y
            x0, y0 = min(x0, tx), min(y0, ty)
            x1, y1 = max(x1, tx + tw), max(y1, ty + w.h)

        return x0, y0, x1 - x0, y1 - y0

    def sammle(widgets, pfad):
        for wi, w in enumerate(widgets):
            x, y, breite, hoehe = ausdehnung(w)
            kacheln.append({
                "pfad": pfad + ["widgets", wi],
                "x": x, "y": y, "w": breite, "h": hoehe,
                "zelle": [w.x, w.y, w.w, w.h],
                "typ": w.type,
                "raster": bool(w.cell_benutzt),
            })

    def bereich(pfad, r, typ):
        """Ein benannter Bereich (`region`) — Meldezeile und Screen-Gruppe.

        ⚠ Die haben keine Kacheln, aber sehr wohl eine Flaeche. Ohne sie blieb beim
        Anwaehlen der Meldezeile in der Vorschau alles unmarkiert, und man konnte nicht
        sehen, wo sie eigentlich liegt.
        """
        if not r:
            return
        x, y, breite, hoehe = r
        kacheln.append({
            "pfad": pfad, "x": x, "y": y, "w": breite, "h": hoehe,
            "zelle": [x, y, breite, hoehe], "typ": typ,
            "raster": False, "feld": "region",
        })

    sammle(panel.widgets, ["panels", pi])
    for gi, gruppe in enumerate(panel.groups):
        bereich(["panels", pi, "screen_groups", gi], gruppe.region, "screen_group")
        name = aktiv.get(gruppe.id)
        for si, screen in enumerate(gruppe.screens):
            if screen.name != name:
                continue        # nur der sichtbare Screen ist anklickbar
            # ⚠ Und davon nur die sichtbare SEITE: die Kacheln der anderen liegen an
            # denselben Stellen, ein Klick landete sonst auf einer Kachel, die man gar
            # nicht sieht — und man bearbeitet ahnungslos die falsche.
            sj = seiten.get(gruppe.id, 0) if seiten else 0
            sj = min(sj, len(screen.seiten) - 1)
            if len(screen.seiten) > 1:
                sammle(screen.seiten[sj].widgets,
                       ["panels", pi, "screen_groups", gi, "screens", si, "seiten", sj])
            else:
                sammle(screen.widgets,
                       ["panels", pi, "screen_groups", gi, "screens", si])
    bereich(["panels", pi, "notify"], panel.notify.region, "notify")
    return kacheln


def _rein(daten):
    """ruamel-Strukturen in schlichtes JSON-Material verwandeln."""
    if isinstance(daten, dict):
        return {str(k): _rein(v) for k, v in daten.items()}
    if isinstance(daten, list):
        return [_rein(v) for v in daten]
    return daten
