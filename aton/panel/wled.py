"""Uebertragung an WLED.

Uebernommen aus der bisherigen Anlage, weil dort jede Zahl am Geraet gemessen ist:

  ganzes Bild, alle Laeufe            33,6 kB   > Anfragegrenze (~16 kB, dann HTTP 413)
  ganzes Bild, nur helle Laeufe       17,4 kB   knapp drueber
  nur die Aenderungen zweier Bilder    1,1 kB   ← 69 von 8192 Pixeln, 0,8 %

Deshalb Differenzuebertragung, und in grossen Abstaenden ein Vollbild als Wiederaufsetz-
punkt (auch nach einem WLED-Neustart). WLED loescht ein Segment beim ERSTEN `i`-Schreib-
vorgang auf Schwarz und friert es ein; danach sind weitere Schreibvorgaenge additiv
(json.cpp: "freeze and init to black" nur wenn `!seg.freeze`). Inkrementelles Zeichnen ist
also vorgesehen und kein Trick.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import aiohttp
from PIL import Image

from .config import PanelCfg
from .icons import _hex2rgb
from .pixel import bild_zu_pixeln, differenz, laeufe_kodieren

_LOG = logging.getLogger(__name__)

CHUNK = 900          # Werte je Anfrage — bleibt unter der ~16-kB-Grenze


@dataclass
class Statistik:
    frames: int = 0
    vollbilder: int = 0
    letzte_pixel: int = 0
    letzte_bytes: int = 0
    fehler: int = 0            # Gesamtzahl seit dem Start — bleibt stehen
    letzter_fehler: str = ""   # ⚠ nur der AKTUELLE Zustand, siehe unten
    erreichbar: bool = False


class WledTransport:
    def __init__(self, panel: PanelCfg):
        self.panel = panel
        self.stat = Statistik()
        self._letztes: list[str] | None = None
        # Zuletzt ans Geraet geschickte Helligkeit. None = noch keine — dann geht sie
        # ohnehin mit dem ersten Vollbild raus.
        self._letzte_bri: int | None = None
        self._zaehler = 0
        self._scroll_aktiv = False
        self._scroll_signatur: object = "_init_"
        self._defekt = False

    def vollbild_erzwingen(self) -> None:
        """Naechstes Bild vollstaendig senden (nach WLED-Neustart oder auf Zuruf)."""
        self._letztes = None

    # ------------------------------------------------------------------
    async def sende(self, session: aiohttp.ClientSession, bild: Image.Image, bri: int,
                    scroll: tuple[str, str, str] | None) -> None:
        p = self.panel
        pixel = bild_zu_pixeln(bild)
        self._zaehler += 1
        vollbild = (self._letztes is None) or (self._zaehler % p.full_frame_every == 0)

        rahmen = {"id": p.canvas_segment, "on": True, "bri": bri, "pal": 0, "fx": 0,
                  "frz": True, "start": 0, "stop": p.width, "startY": 0, "stopY": p.height}

        gesendet = 0
        if vollbild:
            # ★★ Das Vollbild kodiert JEDEN Lauf, auch die schwarzen. Damit BESCHREIBT es
            # die Flaeche, statt sie nur zu ergaenzen — und braucht kein Schwarzfuellen
            # davor.
            #
            # Vorgeschichte, damit niemand das Fuellen "zurueckrepariert": WLED loescht
            # ein Segment beim Schreiben eines `i`-Arrays nur, solange es NICHT
            # eingefroren ist (json.cpp: "freeze and init to black" nur wenn
            # `!seg.freeze`). Die Bildflaeche laeuft dauerhaft mit `frz: true`, der
            # Rahmen mit `i: []` leert also gar nichts. Solange die Kodierung schwarze
            # Laeufe wegliess, konnte ein Vollbild ein faelschlich leuchtendes Pixel
            # nicht zuruecknehmen — am 31.07.2026 auf der Wohnzimmer-Matrix gesehen:
            # Pixel (14,58) leuchtete ueber mehrere Anker hinweg weiter. Die Reparatur
            # war damals ein ausdruecklicher schwarzer Bereich ueber die ganze Flaeche.
            #
            # ⚠ Der aber blendete die Matrix aus: zwischen dem Leeren und dem letzten
            # Block des Neuaufbaus war sie dunkel — alle `full_frame_every` Bilder ein
            # sichtbares Flackern (bei 60 und 5 s Takt: alle fuenf Minuten). Schwarze
            # Laeufe mitzukodieren loest beides: das falsche Pixel wird ausdruecklich
            # schwarz UEBERSCHRIEBEN statt durch Leeren entfernt, und dunkel wird die
            # Flaeche nie.
            #
            # Preis, am echten Bild gemessen (8192 Pixel, 6803 davon schwarz): 4782 statt
            # 2535 Werte, 34 statt 18 kB JSON, 7 statt 4 Bloecke — alle fuenf Minuten.
            arr = laeufe_kodieren(pixel, mit_schwarz=True)
            erst = dict(rahmen, i=[])
            gesendet += await self._post(session, {"on": True, "seg": [erst]})
            # ⚠ Ein "seg"-Array mit wenigen Eintraegen loescht die uebrigen NICHT (am Geraet
            # geprueft). Alte Kachelsegmente haetten hoehere Nummern als die Bildflaeche und
            # wuerden sie ueberdecken — also ausdruecklich entfernen. Weil ab der Nummer nach
            # dem Scroll-Segment ALLES faellt, entstehen keine ID-Luecken, die WLEDs
            # Oberflaeche stoeren ("can't access property classList").
            # ⚠ Nicht ueber WLEDs MAX_NUM_SEGMENTS hinaus aufraeumen — Segmentnummern,
            # die es gar nicht gibt, sind bestenfalls wirkungslos. Vorgabe 32 = der
            # Standard auf ESP32; wer eine Firmware mit mehr Segmenten faehrt und noch
            # Altlasten oberhalb hat, setzt `clear_segments_to` hoeher.
            gesendet += await self._post(session, {"seg": [
                {"id": n, "stop": 0}
                for n in range(p.scroll_segment + 1, p.clear_segments_to)]})
            self.stat.vollbilder += 1
            self.stat.letzte_pixel = len(pixel)
        else:
            arr = differenz(pixel, self._letztes)
            self.stat.letzte_pixel = len(arr) // 2

            # ★★ Die Helligkeit haengt am `rahmen` — und der geht NUR beim Vollbild raus.
            # Ein neuer Wert kam damit erst beim naechsten turnusmaessigen Vollbild an:
            # bei `full_frame_every: 60` und 5 s Takt bis zu FUENF MINUTEN. Am Geraet
            # erlebt, der Regler wirkte scheinbar gar nicht.
            #
            # Also bei Aenderung ausdruecklich nachschicken. Nur bei Aenderung: ein `bri`
            # in jedem Bild waere eine Anfrage mehr im 5-Sekunden-Takt, fuer einen Wert,
            # der sich fast nie bewegt.
            if bri != self._letzte_bri:
                gesendet += await self._post(
                    session, {"seg": [{"id": p.canvas_segment, "bri": bri}]})

        for k in range(0, len(arr), CHUNK):
            gesendet += await self._post(
                session, {"seg": [{"id": p.canvas_segment, "i": arr[k:k + CHUNK]}]})

        self._letzte_bri = bri
        self._letztes = pixel
        self.stat.frames += 1
        self.stat.letzte_bytes = gesendet

        # ★ Fehlermeldung wieder wegnehmen, wenn dieses Bild sauber durchging.
        # Vorher blieb `letzter_fehler` fuer immer stehen — die Oberflaeche zeigte dann
        # stundenlang „nicht erreichbar", obwohl laengst wieder alles lief. Eine Anzeige,
        # die den aktuellen Zustand falsch behauptet, ist schlimmer als gar keine.
        # Der Zaehler `fehler` bleibt kumulativ: dass es geknirscht hat, soll sichtbar
        # bleiben — nur eben als Zaehler und nicht als Dauerwarnung.
        if not self._defekt:
            self.stat.letzter_fehler = ""

        if self._defekt:
            # Waehrend des Sendens ist etwas schiefgegangen — was jetzt auf dem Geraet
            # steht, weiss niemand. Also beim naechsten Mal wieder ein Vollbild, sonst
            # rechnet die Differenz gegen ein Bild, das es dort gar nicht gibt.
            self._letztes = None
            self._defekt = False

        await self._scroll(session, scroll, bri, vollbild)

    # ------------------------------------------------------------------
    async def _scroll(self, session, scroll, bri: int, vollbild: bool) -> None:
        """Laufschrift-Segment pflegen.

        ⚠ Nur bei Aenderung senden — jedes Neusenden setzt WLEDs Animation zurueck, die
        Schrift finge also bei jedem Frame von vorn an. Diese Sperre ist der Grund fuer die
        Signatur; sie ging beim Umbau der alten Anlage einmal verloren und ist am Geraet
        wieder nachgewiesen worden.

        ⚠ Und: Segment 1 muss IMMER existieren. HAs WLED-Anbindung legt die Haupt-Entitaet
        (den echten Aus-Schalter) nur an, solange das Geraet MEHR ALS EIN Segment hat.
        Ohne Laufschrift wird es unsichtbar an den unteren Rand geparkt.
        """
        p = self.panel
        geparkt = {"id": p.scroll_segment, "on": False, "frz": False, "start": 0, "stop": 1,
                   "startY": p.height - 1, "stopY": p.height}

        signatur = scroll[:2] if scroll else None
        geaendert = signatur != self._scroll_signatur
        self._scroll_signatur = signatur

        if scroll:
            if geaendert or not self._scroll_aktiv:
                self._scroll_aktiv = True
                await self._post(session, {"seg": [self._scroll_segment(scroll, bri)]})
            return

        if self._scroll_aktiv:
            self._scroll_aktiv = False
            await self._post(session, {"seg": [geparkt]})
        elif vollbild:
            await self._post(session, {"seg": [geparkt]})

    def _scroll_segment(self, scroll: tuple[str, str, str], bri: int) -> dict:
        """Natives WLED "Scrolling Text" (FX122). Der Text steht im Segmentnamen `n`.

        ★ Die Stufenfarbe steckt in der SCHRIFT, nicht im Hintergrund — absichtlich, damit
        es auf beiden Firmware-Zweigen gleich aussieht:
          WLED-MM  : o2 = "Overlay". Aus -> Hintergrund wird mit col[1] gefuellt.
          mainline : o2 = "Custom Font", einen Overlay-Schalter gibt es nicht mehr, und der
                     Hintergrund wird mit fadeToBlackBy() abgedunkelt statt gefuellt.
        Ein farbiger Hintergrund ist auf mainline also nicht zu bekommen; weiss auf
        vermeintlich rot waere dort weiss auf schwarz — eine Warnung nicht mehr von einer
        Information zu unterscheiden.

        Weitere Fallen (aus FX.cpp nachgesehen): `frz:false` ist zwingend, weil das
        Schreiben eines `i`-Arrays das Segment einfriert und danach KEIN Effekt mehr laeuft.
        `ix` = Y-Versatz (128 = mittig im 8px-Streifen), `c2` = Schrift (128 = 6x8),
        `o1` = Verlauf an + `pal:0` -> Textfarbe = col[0].
        """
        cfg = self.panel.notify
        text, farbe, _ = scroll
        d = {"id": self.panel.scroll_segment, "on": True, "bri": bri, "frz": False,
             "fx": cfg.scroll_fx, "sx": cfg.scroll_speed, "ix": cfg.scroll_yoff,
             "c1": 0, "c2": cfg.scroll_font, "o1": True, "o2": False, "o3": False,
             "pal": 0, "col": [list(_hex2rgb(farbe)), [0, 0, 0], [0, 0, 0]],
             "n": self._scroll_name(text)}
        x, y, w, h = cfg.region
        d["start"], d["stop"], d["startY"], d["stopY"] = x, x + w, y, y + h
        return d

    def _scroll_name(self, text: str) -> str:
        # Die Laufschrift zeichnet WLED selbst — die Schrift der App gilt hier nicht.
        # Umlaute kann WLEDs eingebaute Schrift nicht, deshalb dieselbe Ersatzschreibung
        # wie in der 5x3-Schrift.
        return (str(text).upper().replace("Ä", "AE").replace("Ö", "OE")
                .replace("Ü", "UE").replace("ß", "SS"))[: self.panel.notify.max_chars]

    # ------------------------------------------------------------------
    async def _post(self, session: aiohttp.ClientSession, daten: dict) -> int:
        """Einen Block senden. Rueckgabe: gesendete Bytes (0 bei Fehler).

        ★ Fehlerbehandlung mit Absicht laut: in der Vorgaengerfassung gingen echte
        Sendefehler als Nebensatz unter. WLED antwortet z.B. mit 413, wenn eine Anfrage zu
        gross ist — so etwas MUSS auffallen.
        """
        url = f"http://{self.panel.host}/json/state"
        try:
            roh = _json_bytes(daten)
            async with session.post(url, data=roh,
                                    headers={"Content-Type": "application/json"}) as antwort:
                if antwort.status != 200:
                    text = await antwort.text()
                    self._fehler(f"HTTP {antwort.status}: {text[:200]}")
                    return 0
            self.stat.erreichbar = True
            return len(roh)
        except Exception as e:
            self._fehler(f"nicht erreichbar ({type(e).__name__}: {e})")
            return 0

    def _fehler(self, meldung: str) -> None:
        self.stat.fehler += 1
        self.stat.letzter_fehler = meldung
        self.stat.erreichbar = False
        self._defekt = True
        _LOG.warning("WLED %s (%s): %s", self.panel.id, self.panel.host, meldung)


def _json_bytes(daten: dict) -> bytes:
    return json.dumps(daten, separators=(",", ":")).encode("utf-8")
