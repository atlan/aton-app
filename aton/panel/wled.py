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

import asyncio
import json
import logging
import time
from dataclasses import dataclass

import aiohttp
from PIL import Image

from .config import PanelCfg
from .icons import _hex2rgb
from .pixel import bild_zu_pixeln, differenz, laeufe_kodieren
from .render import ScrollAuftrag

_LOG = logging.getLogger(__name__)

CHUNK = 900          # Werte je Anfrage — bleibt unter der ~16-kB-Grenze

#: Name des von Aton angelegten Boot-Presets. ⚠ Er ist die KENNUNG: nur ein Preset mit
#: genau diesem Namen fasst Aton wieder an. Alles andere auf dem Platz gilt als fremd und
#: bleibt unberuehrt. Deshalb darf er sich nicht mehr aendern — sonst legt eine neue
#: Fassung neben dem alten ein zweites an und ruehrt das alte nie wieder an.
BOOT_PRESET_NAME = "Aton Boot schwarz"

#: Wie oft und mit welchem Abstand nach dem Schreiben nachgesehen wird. WLED legt
#: `presets.json` im Flash ab und beantwortet ein sofortiges GET noch aus dem alten
#: Stand — einmal nachsehen reicht nachweislich nicht.
VERIFY_VERSUCHE = 5
VERIFY_PAUSE_S = 0.4

#: Abstand zwischen dem Zustandsschreiben und dem `psave` — und wie oft der ganze
#: Schreibanlauf wiederholt wird. WLED arbeitet beides in seiner Hauptschleife ab und
#: verschluckt das Speichern, wenn es zu dicht folgt (17.08.2026 am Geraet gemessen).
SPEICHER_PAUSE_S = 1.0
SCHREIB_VERSUCHE = 3

#: Wie viele Zeichen WLEDs Segmentname traegt — und damit eine Laufschrift.
#: `WLED_MAX_SEGNAME_LEN` in WLEDs `const.h`: 48 auf ESP32, 32 auf ESP8266. Die kleinere
#: Zahl zu nehmen kostet nichts und schneidet auf keinem Geraet ueberraschend ab.
MAX_SEGMENTNAME = 32


class Unerreichbar(Exception):
    """Ein Block ist nicht angekommen — der Rest des Bildes waere vergeudet.

    ★★ Warum eine Ausnahme und kein Rueckgabewert: ein Bild geht in bis zu acht Bloecken
    raus, und `sende()` hat sie frueher ALLE geschickt, auch wenn der erste schon in eine
    Zeitueberschreitung gelaufen war. Am 14.08.2026 im Protokoll gemessen — ein einziger
    Takt beim Einschalten der Wohnzimmer-Matrix:

        11:21:21  nicht erreichbar (192.168.1.50)      ← ein Connect-Timeout, ~3 s
        11:21:23  nicht erreichbar   × 7               ← die restlichen Bloecke

    Acht Meldungen, ein Sachverhalt. Der erste Block beantwortet die Frage bereits
    vollstaendig; alles danach kostet nur Zeit und macht aus einem Befund einen Haufen.
    """


@dataclass
class Statistik:
    frames: int = 0
    vollbilder: int = 0
    letzte_pixel: int = 0
    letzte_bytes: int = 0
    fehler: int = 0            # Gesamtzahl seit dem Start — bleibt stehen
    letzter_fehler: str = ""   # ⚠ nur der AKTUELLE Zustand, siehe unten
    erreichbar: bool = False
    #: Seit wann ist das Geraet nicht erreichbar (Unix-Zeit)? 0 = es ist erreichbar.
    #:
    #: ★★ Erreichbarkeit ist ein ZUSTAND, kein Ereignis. Am 14.08.2026 stand die
    #: Entry-Matrix 7,5 Stunden stromlos auf dem Schreibtisch und die App buchte dafuer
    #: **5888 Sendefehler** — 5888 Vorfaelle fuer eine einzige Ursache. Eine Zeile
    #: „nicht erreichbar seit 02:41" sagt dasselbe und stimmt die ganze Zeit ueber.
    unerreichbar_seit: float = 0.0
    #: Ergebnis der letzten Boot-Preset-Pruefung (siehe `bootbild_sichern`). Leer heisst
    #: „noch nicht geprueft"; „in Ordnung" ist der Normalfall.
    bootbild: str = ""


class WledTransport:
    def __init__(self, panel: PanelCfg):
        self.panel = panel
        self.stat = Statistik()
        self._letztes: list[str] | None = None
        # Zuletzt ans Geraet geschickte Helligkeit. None = noch keine — dann geht sie
        # ohnehin mit dem ersten Vollbild raus.
        self._letzte_bri: int | None = None
        self._zaehler = 0
        # Je SEGMENT eine Signatur bzw. ein Aktiv-Merker. Bis 0.21.0 war beides je EINE
        # Variable — es gab ja nur ein Scroll-Segment.
        self._scroll_signaturen: dict[int, object] = {}
        self._scroll_aktive: set[int] = set()
        # Laeuft der gerade gesendete Frame als Erreichbarkeitsprobe? Siehe `_fehler`.
        self._probe = False

    def vollbild_erzwingen(self) -> None:
        """Naechstes Bild vollstaendig senden (nach WLED-Neustart oder auf Zuruf)."""
        self._letztes = None

    # ------------------------------------------------------------------
    async def bootbild_sichern(self, session: aiohttp.ClientSession) -> str:
        """Dafuer sorgen, dass WLED beim Hochfahren SCHWARZ zeigt statt seiner Vorgabe.

        ★★ Das Problem, am 17.08.2026 an allen drei Matrizen der Anlage gemessen: ohne
        Boot-Preset (`cfg.def.ps == 0`) malt WLED beim Einschalten seine eingebaute
        Vorgabefarbe — RGB **255,160,0**, eine vollflaechig orange Leuchtflaeche. Die
        steht, bis Atons erstes Vollbild ankommt, und das dauert: ESP booten, ins WLAN,
        Konfigurationseintrag aktivieren. Bei der Seiten-Matrix waren das ueber zwei
        Minuten. Das Vollbild beim Einschalten (siehe `display._takt`) behebt nur die
        Folge, nicht die Ursache — die Luecke selbst bleibt.

        Diese Methode laeuft beim EINSCHALTEN, also bevor das erste Vollbild rausgeht.
        Der Zeitpunkt ist mit Absicht gewaehlt: dort steht ohnehin noch WLEDs Bootfarbe
        auf der Flaeche, das Schwarzsetzen zerstoert also kein Bild — und dieser Start
        ist gleich mit repariert.

        Rueckgabe: eine kurze Lagebeschreibung fuer Protokoll und Statistik.

        ⚠⚠ Drei Fallen, alle am Geraet erlebt und der Grund fuer den umstaendlichen Ablauf:

        1. **`psave` zusammen mit dem Zustand in EINER Anfrage wird still verworfen.**
           WLED antwortet `{"success":true}` und legt nichts an. Es braucht zwei
           getrennte Anfragen: erst den Zustand setzen, dann speichern.
        2. **Ein eingefrorenes Segment wird nicht neu gezeichnet.** Schreibt man `col`
           auf ein Segment mit `frz: true`, aendert sich das JSON, aber der alte
           Pixelpuffer bleibt stehen — `/json/state` meldet dann Schwarz, waehrend
           physisch weiter Orange leuchtet. Deshalb `"frz": false` beim Setzen.
        3. **`cfg.def.ps` auf ein nicht existierendes Preset ist schlimmer als gar
           keins** und faellt niemandem auf, weil WLED dann einfach wieder seine Vorgabe
           malt. Genau so stand die Entry-Matrix da — eine frueher gescheiterte
           Handanlegung. Deshalb wird am Ende zurueckgelesen.
        """
        p = self.panel
        slot = str(p.boot_preset_slot)
        try:
            presets = await self._get(session, "/presets.json")
            cfg = await self._get(session, "/json/cfg")
        except Unerreichbar as e:
            return f"nicht geprueft ({e})"

        vorhanden = presets.get(slot) or {}
        name = vorhanden.get("n")
        belegt = bool(vorhanden.get("seg") or vorhanden.get("playlist") or name)
        if belegt and name != BOOT_PRESET_NAME:
            # ★ Fremdes Preset: nicht anfassen. Ein Preset ist Handarbeit des Nutzers,
            # und es zu ueberschreiben waere ein stiller Datenverlust.
            _LOG.warning(
                "WLED %s (%s): Preset %s ist mit %s belegt — Aton laesst es in Ruhe. "
                "Die Matrix zeigt beim Einschalten weiter WLEDs Vorgabefarbe. Abhilfe: "
                "`boot_preset_slot` auf einen freien Platz stellen oder `boot_preset: "
                "false` setzen.", p.id, p.host, slot, repr(name) if name else "einem namenlosen Preset")
            return f"Platz {slot} fremd belegt ({name or 'ohne Namen'})"

        schwarz = _ist_schwarz(vorhanden, p.canvas_segment)
        if belegt and schwarz and _boot_ps(cfg) == p.boot_preset_slot:
            # ⚠ Der haeufige Fall — und er darf NICHTS schreiben. `psave` und die
            # Konfiguration gehen in den Flash des ESP; sie bei jedem Einschalten
            # anzufassen waere Verschleiss ohne Gegenwert.
            return "in Ordnung"

        try:
            for anlauf in range(SCHREIB_VERSUCHE):
                await self._setze_schwarz(session)
                # ⚠⚠ Diese Pause ist nicht Zierrat, sie ist der Unterschied zwischen
                # „klappt" und „klappt nicht". WLED arbeitet Zustand und `psave` in seiner
                # Hauptschleife ab; folgt das Speichern zu dicht auf das Schreiben, wird
                # es verschluckt — Antwort `{"success":true}`, `presets.json` unveraendert.
                # Am 17.08.2026 beides gemessen: von Hand mit einer Sekunde Abstand ging
                # es, dieselbe Folge ohne Abstand legte auch nach 2,6 s Nachsehen nichts an.
                await asyncio.sleep(SPEICHER_PAUSE_S)
                await self._post(session, {"psave": p.boot_preset_slot,
                                           "n": BOOT_PRESET_NAME, "ib": True, "sb": True})
                await self._post_cfg(session, {"def": {"ps": p.boot_preset_slot,
                                                       "on": True, "bri": 128}})
                # ⚠ Nicht dem `{"success":true}` glauben — genau das hat gelogen (Falle 1).
                #
                # ⚠ Aber auch nicht zu frueh nachsehen: WLED legt `presets.json` im Flash
                # ab und beantwortet ein sofortiges GET noch aus dem alten Stand. Ein
                # Falschalarm waere teuer — er wuerde bei JEDEM Einschalten neu schreiben.
                for versuch in range(VERIFY_VERSUCHE):
                    if versuch:
                        await asyncio.sleep(VERIFY_PAUSE_S)
                    presets = await self._get(session, "/presets.json")
                    cfg = await self._get(session, "/json/cfg")
                    if (_ist_schwarz(presets.get(slot) or {}, p.canvas_segment)
                            and _boot_ps(cfg) == p.boot_preset_slot):
                        break
                else:
                    continue        # nichts angekommen — ganzen Anlauf wiederholen
                break
        except Unerreichbar as e:
            # Mittendrin abgerissen. Was auf dem Geraet steht, weiss jetzt niemand —
            # also beim naechsten Takt noch einmal, und ein Vollbild dazu.
            self._letztes = None
            return f"nicht geprueft ({e})"

        neu = presets.get(slot) or {}
        if not _ist_schwarz(neu, p.canvas_segment):
            _LOG.warning("WLED %s (%s): Boot-Preset %s liess sich nicht anlegen — die "
                         "Matrix zeigt beim Einschalten weiter WLEDs Vorgabefarbe.",
                         p.id, p.host, slot)
            lage = f"Preset {slot} liess sich nicht anlegen"
        elif _boot_ps(cfg) != p.boot_preset_slot:
            _LOG.warning("WLED %s (%s): Preset %s liegt, aber der Bootweg zeigt nicht "
                         "darauf (cfg.def = %r).", p.id, p.host, slot, cfg.get("def"))
            lage = f"Bootweg zeigt nicht auf Preset {slot}"
        else:
            _LOG.info("WLED %s (%s): Boot-Preset %s angelegt — die Matrix bleibt beim "
                      "Hochfahren dunkel statt orange.", p.id, p.host, slot)
            lage = "angelegt"
        # In JEDEM dieser Faelle steht auf der Flaeche jetzt Schwarz, das Aton selbst
        # geschrieben und nicht gezeichnet hat. Ohne Vollbild bliebe die Matrix dunkel.
        self._letztes = None
        return lage

    async def _setze_schwarz(self, session: aiohttp.ClientSession) -> None:
        """Die Bildflaeche auf Schwarz stellen — sichtbar, nicht nur im JSON.

        ⚠ `"frz": False` ist der Kern: auf einem eingefrorenen Segment aendert eine neue
        Farbe nur den Wert, nicht die Anzeige (Falle 2 oben).
        """
        await self._post(session, {"on": True, "seg": [
            {"id": self.panel.canvas_segment, "on": True, "frz": False,
             "fx": 0, "pal": 0, "col": [[0, 0, 0], [0, 0, 0], [0, 0, 0]]}]})

    # ------------------------------------------------------------------
    async def sende(self, session: aiohttp.ClientSession, bild: Image.Image, bri: int,
                    scroll: list[ScrollAuftrag] | None, probe: bool = False) -> None:
        """Ein Bild ans Geraet schicken.

        `probe=True` heisst: die App weiss selbst nicht, ob dort jemand ist — Home
        Assistant meldet das Tor gerade nicht als `on`, und dieser Versuch soll genau das
        klaeren. Scheitert er, ist das **kein Sendefehler**, sondern die Antwort auf die
        Frage. Gezaehlt wird nur, was scheitert, obwohl HA das Geraet als da fuehrt.
        """
        self._probe = probe
        try:
            await self._frame(session, bild, bri, scroll)
        except Unerreichbar:
            # Was jetzt auf dem Geraet steht, weiss niemand — der Frame ist mittendrin
            # abgebrochen. Also beim naechsten Mal ein Vollbild, sonst rechnet die
            # Differenz gegen ein Bild, das dort gar nicht steht.
            self._letztes = None
            # ⚠ Und die Laufschrift-Sperre muss mit zurueck: `_scroll` merkt sich Text und
            # Zustand, BEVOR es sendet. Ohne diese Zeilen gilt eine Meldung als
            # geschickt, die nie ankam — und weil sie sich danach nicht mehr „aendert",
            # wuerde sie nie wiederholt.
            self._scroll_signaturen.clear()
            self._scroll_aktive.clear()

    async def _frame(self, session: aiohttp.ClientSession, bild: Image.Image, bri: int,
                     scroll: list[ScrollAuftrag] | None) -> None:
        p = self.panel
        pixel = bild_zu_pixeln(bild)
        self._zaehler += 1
        # ★★ Eine geaenderte Helligkeit erzwingt ein VOLLBILD, nicht nur einen `bri`-Block.
        #
        # Auf einem eingefrorenen Segment wirkt die Segmenthelligkeit erst, wenn die Pixel
        # (neu) geschrieben werden — der blosse Wert aendert das stehende Bild nicht. Bei
        # einer Anzeige, deren Inhalt sich staendig bewegt, faellt das nicht auf: der
        # naechste Takt schreibt ohnehin Pixel. Bei einer stehenden faellt es voll auf.
        #
        # Am 14.08.2026 an der Anlage gemessen, sechs Takte je Anzeige:
        #
        #     wohnzimmer (Uhr, Temperaturen)   18–43 Pixel je Takt   → Helligkeit sofort da
        #     wohnzimmer_tv (ToDo-Liste)        0 Pixel in 5 von 6   → Helligkeit unsichtbar
        #     entry                             0 Pixel in 6 von 6   → dito
        #
        # Der User sah es genau so: Regler bewegt, WLED meldet den neuen Wert, die Matrix
        # bleibt wie sie ist — und erst „Vollbild senden" macht sie hell bzw. dunkel.
        # Genau das tut diese Zeile jetzt von selbst.
        #
        # Preis: 34 kB in sieben Bloecken statt 40 Byte, aber nur wenn jemand den Regler
        # anfasst. Eine Helligkeit, die man erst bestaetigen muss, ist keine.
        vollbild = ((self._letztes is None)
                    or (self._zaehler % p.full_frame_every == 0)
                    or (self._letzte_bri is not None and bri != self._letzte_bri))

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
            # ⚠ Der erste Block ist zugleich die Erreichbarkeitsprobe: winzig (`i: []`),
            # geht als Erster raus, und wenn er scheitert, bricht `Unerreichbar` den
            # ganzen Frame ab. Deshalb braucht die App KEINEN eigenen Ping — ein
            # zusaetzlicher Aufruf koennte gelingen, waehrend das echte Schreiben
            # scheitert, und wuerde dann das Falsche beweisen.
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
            # ⚠ AB der Nummer nach der LETZTEN Laufschrift raeumen, nicht nach der ersten:
            # seit 0.21.1 belegen mehrere Meldezeilen aufeinanderfolgende Segmente, und ein
            # `stop: 0` darauf haette die zweite Laufschrift bei jedem Vollbild geloescht.
            gesendet += await self._post(session, {"seg": [
                {"id": n, "stop": 0}
                for n in range(p.hoechstes_scroll_segment + 1, p.clear_segments_to)]})
            self.stat.letzte_pixel = len(pixel)
        else:
            arr = differenz(pixel, self._letztes)
            self.stat.letzte_pixel = len(arr) // 2

            # ⚠ Hier stand bis 0.20.2 ein nachgeschickter `bri`-Block. Er ist entfallen,
            # weil eine Helligkeitsaenderung jetzt weiter oben schon ein Vollbild ausloest
            # — und der blosse Wert ohne neu geschriebene Pixel hat auf einem
            # eingefrorenen Segment ohnehin nichts bewirkt. Wer ihn zurueckholen will,
            # liest erst den Kommentar an `vollbild`.

        for k in range(0, len(arr), CHUNK):
            gesendet += await self._post(
                session, {"seg": [{"id": p.canvas_segment, "i": arr[k:k + CHUNK]}]})

        # ★ Erst hier gezaehlt, nicht beim Aufbau: bis zu dieser Zeile ist jeder Block
        # angekommen. Vorher stand `vollbilder += 1` oben im Zweig und zaehlte auch
        # Vollbilder mit, von denen kein einziges Byte das Geraet erreicht hat.
        if vollbild:
            self.stat.vollbilder += 1
        self._letzte_bri = bri
        self._letztes = pixel
        self.stat.frames += 1
        self.stat.letzte_bytes = gesendet

        # ★ Fehlermeldung wieder wegnehmen, wenn dieses Bild sauber durchging.
        # Vorher blieb `letzter_fehler` fuer immer stehen — die Oberflaeche zeigte dann
        # stundenlang „nicht erreichbar", obwohl laengst wieder alles lief. Eine Anzeige,
        # die den aktuellen Zustand falsch behauptet, ist schlimmer als gar keine.
        self.stat.letzter_fehler = ""

        await self._scrolls(session, scroll, bri, vollbild)

    # ------------------------------------------------------------------
    async def _scrolls(self, session, auftraege, bri: int, vollbild: bool) -> None:
        """Die Laufschrift-Segmente pflegen — seit 0.21.1 mehrere gleichzeitig.

        ⚠ Nur bei Aenderung senden — jedes Neusenden setzt WLEDs Animation zurueck, die
        Schrift finge also bei jedem Frame von vorn an. Diese Sperre ist der Grund fuer die
        Signatur; sie ging beim Umbau der alten Anlage einmal verloren und ist am Geraet
        wieder nachgewiesen worden. Sie gilt jetzt JE SEGMENT: eine neue Meldung in Zeile 2
        darf die laufende Schrift in Zeile 1 nicht von vorn beginnen lassen.

        ⚠ Und: das erste Scroll-Segment muss IMMER existieren. HAs WLED-Anbindung legt die
        Haupt-Entitaet (den echten Aus-Schalter) nur an, solange das Geraet MEHR ALS EIN
        Segment hat. Ohne Laufschrift wird es unsichtbar an den unteren Rand geparkt.
        """
        p = self.panel
        auftraege = list(auftraege or [])
        jetzt = {a.segment: a for a in auftraege}

        # Was gerade laeuft und nicht mehr gebraucht wird, wird geparkt. Ohne das bliebe
        # eine erledigte Meldung als Laufschrift stehen — der Bildspeicher darunter ist
        # schwarz, sie wuerde also nie von selbst verschwinden.
        for segment in sorted(self._scroll_aktive - set(jetzt)):
            self._scroll_aktive.discard(segment)
            self._scroll_signaturen.pop(segment, None)
            await self._post(session, {"seg": [self._geparkt(segment)]})

        for segment in sorted(jetzt):
            auftrag = jetzt[segment]
            # Text, Farbe und Flaeche entscheiden — dieselbe Meldung in einer ANDEREN
            # Meldezeile ist eine andere Laufschrift.
            signatur = (auftrag.text, auftrag.bg, auftrag.region)
            if signatur != self._scroll_signaturen.get(segment) \
                    or segment not in self._scroll_aktive:
                self._scroll_signaturen[segment] = signatur
                self._scroll_aktive.add(segment)
                await self._post(session, {"seg": [self._scroll_segment(auftrag, bri)]})

        # ★ Beim Vollbild das erste Segment ausdruecklich parken, wenn dort nichts laeuft —
        # sonst koennte es nach einem WLED-Neustart fehlen, und HA legt den Hauptschalter
        # nur bei MEHR ALS EINEM Segment an.
        if vollbild and p.scroll_segment not in jetzt:
            await self._post(session, {"seg": [self._geparkt(p.scroll_segment)]})

    def _geparkt(self, segment: int) -> dict:
        """Ein Scroll-Segment unsichtbar an den unteren Rand stellen, statt es zu loeschen."""
        p = self.panel
        return {"id": segment, "on": False, "frz": False, "start": 0, "stop": 1,
                "startY": p.height - 1, "stopY": p.height}

    def _scroll_segment(self, scroll: ScrollAuftrag, bri: int) -> dict:
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
        d = {"id": scroll.segment, "on": True, "bri": bri, "frz": False,
             "fx": scroll.fx, "sx": scroll.speed, "ix": scroll.yoff,
             "c1": 0, "c2": scroll.font, "o1": True, "o2": False, "o3": False,
             "pal": 0, "col": [list(_hex2rgb(scroll.bg)), [0, 0, 0], [0, 0, 0]],
             "n": self._scroll_name(scroll.text)}
        x, y, w, h = scroll.region
        d["start"], d["stop"], d["startY"], d["stopY"] = x, x + w, y, y + h
        return d

    def _scroll_name(self, text: str) -> str:
        # Die Laufschrift zeichnet WLED selbst — die Schrift der App gilt hier nicht.
        # Umlaute kann WLEDs eingebaute Schrift nicht, deshalb dieselbe Ersatzschreibung
        # wie in der 5x3-Schrift. Auf `max_chars` ist der Text schon im Renderer gekuerzt.
        # ⚠⚠ WLEDs Segmentname ist begrenzt: `WLED_MAX_SEGNAME_LEN` ist auf ESP32 **48**
        # (`const.h`), auf ESP8266 32. Atons `max_chars` steht per Vorgabe auf 60 — eine
        # lange Meldung wurde also vom GERAET abgeschnitten, ohne dass irgendwo etwas
        # stand. Beim Umbau auf mehrere Laufschriften am WLED-Quelltext aufgefallen.
        # Hier wird sie sichtbar gekuerzt; die Meldezeile hat ihre eigene Grenze
        # (`max_chars`), die weiterhin zuerst greift, wenn sie kleiner ist.
        sauber = (str(text).upper().replace("Ä", "AE").replace("Ö", "OE")
                  .replace("Ü", "UE").replace("ß", "SS"))
        return sauber[:MAX_SEGMENTNAME]

    # ------------------------------------------------------------------
    async def _get(self, session: aiohttp.ClientSession, pfad: str) -> dict:
        """Etwas vom Geraet lesen. Wirft `Unerreichbar` im Fehlerfall.

        ⚠ Anders als `_post` verbucht das hier KEINEN Sendefehler: gelesen wird nur fuer
        die Boot-Preset-Pruefung, und die ist eine Nebensache. Faellt sie aus, ist das
        kein Grund, die Anzeige als gestoert zu melden.

        ⚠⚠ Der Rueckgabewert ist IMMER ein Woerterbuch. Am 17.08.2026 am Geraet
        aufgeflogen: unmittelbar nach einem Konfigurationsschreibvorgang antwortet WLED
        auf `GET /json/cfg` mit einem nackten `null` — HTTP 200, gueltiges JSON, aber
        `None`. Jede Auswertestelle einzeln dagegen abzusichern hat schon einmal nicht
        gereicht (erst war `cfg["def"]` leer, dann `cfg` selbst); die Umwandlung gehoert
        an die eine Stelle, an der gelesen wird.
        """
        url = f"http://{self.panel.host}{pfad}"
        try:
            async with session.get(url) as antwort:
                if antwort.status != 200:
                    raise Unerreichbar(f"HTTP {antwort.status} auf {pfad}")
                nutzlast = await antwort.json(content_type=None)
        except Unerreichbar:
            raise
        except Exception as e:
            raise Unerreichbar(f"{type(e).__name__}: {e}") from e
        return nutzlast if isinstance(nutzlast, dict) else {}

    async def _post_cfg(self, session: aiohttp.ClientSession, daten: dict) -> None:
        """In WLEDs Konfiguration schreiben (`/json/cfg`), nicht in den Zustand."""
        url = f"http://{self.panel.host}/json/cfg"
        try:
            async with session.post(url, data=_json_bytes(daten),
                                    headers={"Content-Type": "application/json"}) as a:
                if a.status != 200:
                    raise Unerreichbar(f"HTTP {a.status} auf /json/cfg")
        except Unerreichbar:
            raise
        except Exception as e:
            raise Unerreichbar(f"{type(e).__name__}: {e}") from e

    async def _post(self, session: aiohttp.ClientSession, daten: dict) -> int:
        """Einen Block senden. Rueckgabe: gesendete Bytes. Wirft `Unerreichbar` im Fehlerfall.

        ★ Fehlerbehandlung mit Absicht laut: in der Vorgaengerfassung gingen echte
        Sendefehler als Nebensatz unter. WLED antwortet z.B. mit 413, wenn eine Anfrage zu
        gross ist — so etwas MUSS auffallen.
        """
        url = f"http://{self.panel.host}/json/state"
        roh = _json_bytes(daten)
        try:
            async with session.post(url, data=roh,
                                    headers={"Content-Type": "application/json"}) as antwort:
                meldung = (None if antwort.status == 200
                           else f"HTTP {antwort.status}: {(await antwort.text())[:200]}")
        except Exception as e:
            meldung = f"nicht erreichbar ({type(e).__name__}: {e})"
        if meldung is not None:
            self._fehler(meldung)
            raise Unerreichbar(meldung)
        self.stat.erreichbar = True
        self.stat.unerreichbar_seit = 0.0
        return len(roh)

    def _fehler(self, meldung: str) -> None:
        """Einen gescheiterten Block verbuchen.

        ★★ Die Trennlinie: gezaehlt wird nur, was scheitert, obwohl Home Assistant das
        Geraet als erreichbar fuehrt. Ein Versuch, mit dem die App erst herausfindet, OB
        dort jemand ist (`probe`), ist keine Stoerung, sondern eine Messung — er setzt
        den Zustand, aber nicht den Zaehler. Sonst stehen fuer eine Matrix, die eine
        Nacht lang stromlos war, tausende „Vorfaelle" mit einer einzigen Ursache.

        ⚠ Nicht zu verwechseln mit Wegschauen: scheitert ein Block, WAEHREND das Tor
        `on` meldet, wird er weiterhin gezaehlt und protokolliert. Dann stimmt etwas
        nicht, und das soll auffallen.
        """
        if not self._probe:
            self.stat.fehler += 1
        self.stat.letzter_fehler = meldung
        self.stat.erreichbar = False
        if not self.stat.unerreichbar_seit:
            self.stat.unerreichbar_seit = time.time()
        _LOG.log(logging.INFO if self._probe else logging.WARNING,
                 "WLED %s (%s): %s%s", self.panel.id, self.panel.host, meldung,
                 "  (Probe — Tor meldet kein 'on')" if self._probe else "")


def _json_bytes(daten: dict) -> bytes:
    return json.dumps(daten, separators=(",", ":")).encode("utf-8")


def _boot_ps(cfg: dict) -> int | None:
    """Auf welches Preset zeigt der Bootweg? `None`, wenn auf keins.

    ⚠⚠ Am Geraet aufgefallen und nicht im Attrappen-Test: WLED antwortet auf ein `GET
    /json/cfg` **unmittelbar nach** einem Konfigurationsschreibvorgang mit
    `{"def": null}` — der Schluessel ist also da, aber leer. `cfg.get("def", {})` greift
    nur bei FEHLENDEM Schluessel und liefert dann None; der Zugriff darauf flog mit
    `AttributeError` aus der Pruefung heraus. Deshalb `or {}` statt eines Vorgabewerts.
    """
    d = cfg.get("def") or {}
    try:
        return int(d.get("ps"))
    except (TypeError, ValueError):
        return None


def _ist_schwarz(preset: dict, segment: int) -> bool:
    """Malt dieses Preset die Bildflaeche schwarz?

    Geprueft wird die Primaerfarbe des Bildsegments — sie ist es, die WLED bei `fx: 0`
    (Solid) ueber die ganze Flaeche legt. ⚠ Nicht ueber die blosse Existenz des Presets
    gehen: bei der Entry-Matrix zeigte `cfg.def.ps` auf einen Platz, auf dem nichts lag.
    """
    for seg in preset.get("seg") or []:
        if seg.get("id", 0) != segment:
            continue
        farben = seg.get("col") or []
        return bool(farben) and list(farben[0])[:3] == [0, 0, 0]
    return False
