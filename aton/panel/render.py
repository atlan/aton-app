"""Das Bild bauen — reine Rechnerei, kein Netz.

Dieses Modul haengt weder an Home Assistant noch an WLED: es bekommt eine Zustandsquelle
(irgendetwas mit `.state()`/`.attr()`) und liefert ein Bild. Genau deshalb laesst es sich
ohne HA und ohne Matrix testen — man setzt ein dict als Quelle ein und vergleicht das
Ergebnis pixelweise.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image, ImageDraw

from .config import IconSpec, PanelCfg, TextSpec, Widget
from .const import DEFAULT_COLOR, UNAVAILABLE_STATES
from .fonts import FontRegistry
from .icons import IconRegistry, _hex2rgb
from .templates import TemplateEngine, TemplateError

_LOG = logging.getLogger(__name__)

WOCHENTAG_BALKEN_Y = 7          # Zeile des Wochentagsbalkens innerhalb der 8px-Kachel


@dataclass
class RenderErgebnis:
    bild: Image.Image
    aktive_screens: dict[str, str] = field(default_factory=dict)
    aktive_seiten: dict[str, int] = field(default_factory=dict)
    scroll_text: tuple[str, str, str] | None = None      # (Text, Hintergrund, Schrift)
    fehler: list[str] = field(default_factory=list)


class Renderer:
    def __init__(self, panel: PanelCfg, quelle, fonts: FontRegistry, icons: IconRegistry):
        self.panel = panel
        self.quelle = quelle
        self.fonts = fonts
        self.icons = icons
        self.tmpl = TemplateEngine(quelle)
        self._gemeldet: set[str] = set()      # Fehler nur einmal je Stelle ins Protokoll

    # ==================================================================
    #  Werte aufloesen
    # ==================================================================
    def _zahl(self, entity_id: str, attribut: str | None = None) -> float | None:
        roh = (self.quelle.attr(entity_id, attribut) if attribut
               else self.quelle.state(entity_id))
        if roh in UNAVAILABLE_STATES:
            return None
        try:
            return float(roh)
        except (TypeError, ValueError):
            return None

    def _text(self, spec: TextSpec) -> str:
        if spec.template:
            return self.tmpl.render(spec.template)
        if spec.literal is not None:
            return str(spec.literal)

        if spec.format is None and spec.decimals is None:
            roh = (self.quelle.attr(spec.entity, spec.attribute) if spec.attribute
                   else self.quelle.state(spec.entity))
            return spec.unavailable if roh in UNAVAILABLE_STATES else str(roh)

        wert = self._zahl(spec.entity, spec.attribute)
        if wert is None:
            return spec.unavailable
        wert *= spec.scale
        if spec.decimals is not None:
            # Wie der bisherige Renderer: runden und die Python-Schreibweise nehmen —
            # das laesst nachlaufende Nullen weg (12.30 -> "12.3").
            return str(round(wert, spec.decimals))
        return spec.format.format(wert)

    def _farbe(self, wert: str | IconSpec) -> str:
        """Farbe kann fest sein oder — wie ein Symbol — aus dem Zustand kommen."""
        if isinstance(wert, str):
            return wert
        return self._icon(wert) or DEFAULT_COLOR

    def _icon(self, spec: IconSpec) -> str | None:
        if spec.template:
            return self.tmpl.render(spec.template) or None
        if spec.steps:
            wert = self._zahl(spec.entity)
            if wert is not None:
                for schwelle, name in spec.steps:      # absteigend sortiert
                    if wert >= schwelle:
                        return name
            return spec.default or spec.name
        if spec.map:
            zustand = self.quelle.state(spec.entity)
            if zustand in spec.map:
                return spec.map[zustand]
            return spec.default or spec.name
        return spec.name

    # ==================================================================
    #  Zeichnen
    # ==================================================================
    def _schreibe(self, bild: Image.Image, text: str, x: int, y: int, breite: int,
                  hoehe: int, farbe: str, font_name: str, align: str = "left") -> None:
        """Text in ein Feld schreiben — was nicht hineinpasst, wird abgeschnitten.

        ⚠ Unterschied zum bisherigen Renderer: dort lief zu langer Text in die naechste
        Pixelzeile desselben Feldes ueber (die Indexrechnung faltete ihn um). Hier wird
        sauber abgeschnitten. Bei den bestehenden Kacheln passt der Text, das Bild bleibt
        also gleich — nur der Ueberlauf sieht jetzt nach Ueberlauf aus statt nach Salat.
        """
        if not text:
            return
        font = self.fonts.get(font_name)
        rgb = _hex2rgb(farbe)
        feld = Image.new("RGBA", (max(breite, 1), max(hoehe, 1)), (0, 0, 0, 0))
        d = ImageDraw.Draw(feld)
        tx = 1                      # 1 px Rand links, wie in der bisherigen Anlage
        if align != "left":
            tw, _ = font.measure(text)
            tx = (breite - tw) // 2 if align == "center" else breite - tw - 1
        font.draw(d, (tx, 1), text, rgb)
        bild.paste(feld, (x, y), feld)

    def _symbol(self, bild: Image.Image, name: str, x: int, y: int) -> None:
        symbol = self.icons.get(name)
        bild.paste(symbol, (x, y), symbol)

    def _widget(self, bild: Image.Image, w: Widget) -> None:
        g = self.panel.grid

        if w.bg:
            ImageDraw.Draw(bild).rectangle([w.x, w.y, w.x + w.w - 1, w.y + w.h - 1],
                                          fill=_hex2rgb(w.bg))

        if w.type == "rect":
            return

        if w.type == "image":
            self._symbol(bild, w.image, w.x, w.y)
            return

        if w.type == "calendar":
            self._kalenderblatt(bild, w)
            return

        if w.type == "clock":
            self._uhr(bild, w)
            return

        if w.icon and w.type in ("tile", "icon"):
            name = self._icon(w.icon)
            if name:
                self._symbol(bild, name, w.x, w.y)

        if w.text and w.type in ("tile", "text"):
            if w.type == "tile":
                tx = w.text_x if w.text_x is not None else w.x + g.icon_width + g.gap
                ty = w.text_y if w.text_y is not None else w.y
                tw = w.text_w if w.text_w is not None else w.w - g.icon_width - g.gap
            else:
                tx = w.text_x if w.text_x is not None else w.x
                ty = w.text_y if w.text_y is not None else w.y
                tw = w.text_w if w.text_w is not None else w.w
            self._schreibe(bild, self._text(w.text), tx, ty, tw, w.h,
                           self._farbe(w.color), w.font, w.align)

    # -- eingebaute Sonderkacheln -----------------------------------------
    def _kalenderblatt(self, bild: Image.Image, w: Widget) -> None:
        """Kalenderblatt 9x8: rote Kopfzeile, weisses Blatt, Tageszahl ausgespart."""
        blatt = self.icons.get("cal").copy()
        tag = str(datetime.now().day)
        font = self.fonts.get(w.font)
        xoff = 3 if len(tag) == 1 else 1
        loch = Image.new("RGBA", blatt.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(loch)
        font.draw(d, (xoff, 2), tag, (0, 0, 0))
        # Die Ziffern werden ausgestanzt, nicht aufgemalt: das Blatt ist weiss.
        for y in range(blatt.size[1]):
            for x in range(blatt.size[0]):
                if loch.getpixel((x, y))[3]:
                    blatt.putpixel((x, y), (0, 0, 0, 255))
        bild.paste(blatt, (w.x, w.y), blatt)

    def _uhr(self, bild: Image.Image, w: Widget) -> None:
        """Uhrzeit HH:MM plus Wochentagsbalken darunter."""
        jetzt = datetime.now()
        breite = w.text_w if w.text_w is not None else w.w
        feld = Image.new("RGBA", (breite, w.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(feld)
        self.fonts.get(w.font).draw(d, (3, 1), jetzt.strftime("%H:%M"),
                                    _hex2rgb(self._farbe(w.color)))
        for k in (1, 2, 4, 5, 7, 8, 10, 11, 13, 14, 16, 17, 19, 20):
            d.point((k, WOCHENTAG_BALKEN_Y), fill=(0x88, 0x88, 0x88))
        heute = jetzt.weekday()
        d.point((1 + heute * 3, WOCHENTAG_BALKEN_Y), fill=(255, 255, 255))
        d.point((2 + heute * 3, WOCHENTAG_BALKEN_Y), fill=(255, 255, 255))
        bild.paste(feld, (w.x, w.y), feld)

    # ==================================================================
    #  Ein Frame
    # ==================================================================
    def _screen_waehlen(self, gruppe, vorwahl: str | None, fehler: list[str]):
        """Welcher Screen der Gruppe ist dran?

        Vorwahl (aus HA) schlaegt alles. Sonst gewinnt der erste Screen, dessen `when`
        zutrifft; hat keiner eine Bedingung oder trifft keine zu, gilt der erste Screen
        ohne Bedingung als Rueckfall — und wenn es auch den nicht gibt, der erste ueberhaupt.
        Nie nichts: eine leere Region ist ein Loch im Bild.

        ★ Ist `wechsel_s` gesetzt, wechseln sich **gleichrangige** Screens ab: alle mit
        derselben Bedingung wie der Gewinner (`when: always` und ein fehlendes `when`
        sind dabei dasselbe, siehe config.py). Damit bleibt die Reihenfolge weiterhin
        Vorrang — ein bedingter Screen verdraengt die Rueckfaelle wie bisher — und
        „mehrere Screens fuer denselben Fall" heisst Abwechslung statt „der erste
        gewinnt immer".

        ⚠ Der Zeitpunkt kommt aus der Uhr, nicht aus einem Zaehler: so haengt der
        Wechsel nicht daran, wie oft gerendert wurde (Vorschau im Konfigurator,
        Nachzeichnen wegen einer Benachrichtigung), und zwei Panels mit gleichem Takt
        laufen synchron statt auseinander.
        """
        if vorwahl:
            for s in gruppe.screens:
                if s.name == vorwahl:
                    return s

        gewinner = None
        for s in gruppe.screens:
            if s.when:
                try:
                    if self.tmpl.truthy(s.when):
                        gewinner = s
                        break
                except TemplateError as e:
                    fehler.append(f"{gruppe.id}/{s.name}: {e}")
        if gewinner is None:
            gewinner = next((s for s in gruppe.screens if not s.when), gruppe.screens[0])

        return gewinner

    def _seite_waehlen(self, screen, vorgabe: int | None = None) -> int:
        """Welche Seite des Screens ist dran?

        ★ Der Wechsel sitzt IM Screen, nicht zwischen Screens. Das ist der Unterschied,
        auf den es ankommt: in der Auswahl (HA-`select`) steht weiterhin nur der Screen,
        und der Wechsel laeuft deshalb genauso weiter, wenn jemand ihn von Hand
        auswaehlt. Waeren es zwei Screens, waeren es zwei Stellungen — und die
        Handauswahl haette den Wechsel angehalten.

        ⚠ Gezaehlt wird in Zyklen (Bildtakten), gerechnet mit der UHR: ein echter
        Bildzaehler wuerde von der Vorschau im Konfigurator mit hochgezaehlt, und zwei
        Anzeigen liefen mit der Zeit auseinander.

        ★ `vorgabe` haelt genau diese Uhr fuer EINEN Aufruf an — sie kommt nur aus dem
        Konfigurator. Ohne sie zeigte die Vorschau die gerade faellige Seite, egal welche
        im Baum angewaehlt war: wer auf „Feuchte" klickte, sah weiter Temperaturen und
        suchte den Fehler in seiner Beschreibung. Der Betrieb uebergibt nichts und rechnet
        unveraendert mit der Uhr — sonst liefen die Anzeigen wieder auseinander, wovor der
        Absatz darueber warnt.
        """
        if len(screen.seiten) < 2 or screen.wechsel_zyklen <= 0:
            return 0
        if vorgabe is not None:
            # Zurechtbiegen statt abweisen: der Baum im Konfigurator kann waehrend des
            # Bearbeitens auf eine Seite zeigen, die es im Entwurf schon nicht mehr gibt.
            return max(0, min(int(vorgabe), len(screen.seiten) - 1))

        # ★ Ungleiche Standzeiten: jede Seite darf mit `zyklen` sagen, wie lange SIE
        # steht; 0 heisst „so lange wie im Screen eingestellt". Damit geht
        # „Uebersicht 2 Zyklen, Details 1", ohne dass eine Seite ohne eigene Angabe
        # etwas merkt.
        #
        # ⚠ `wechsel_zyklen` bleibt der Hauptschalter: steht er auf 0, wechselt gar
        # nichts, auch wenn einzelne Seiten eine Zahl tragen. Sonst waere die
        # dokumentierte Bedeutung „0 = nur die erste" je nach Seiteninhalt mal wahr
        # und mal nicht.
        takte = [(s.zyklen or screen.wechsel_zyklen) for s in screen.seiten]
        gesamt = sum(takte) * self.panel.interval
        if gesamt <= 0:
            return 0
        # Weiter mit der UHR gerechnet, nicht mit einem Bildzaehler — siehe oben.
        # Bei gleichen Standzeiten faellt das hier auf die alte Formel zurueck:
        # floor(t/d) % n. Bestehende Beschreibungen wechseln also unveraendert.
        t = time.time() % gesamt
        for j, takt in enumerate(takte):
            t -= takt * self.panel.interval
            if t < 0:
                return j
        return len(screen.seiten) - 1

    def frame(self, vorwahl: dict[str, str | None] | None = None,
              notiz: dict | None = None,
              seiten_vorwahl: dict[str, int] | None = None) -> RenderErgebnis:
        vorwahl = vorwahl or {}
        seiten_vorwahl = seiten_vorwahl or {}
        bild = Image.new("RGB", (self.panel.width, self.panel.height), (0, 0, 0))
        ergebnis = RenderErgebnis(bild=bild)

        for w in self.panel.widgets:
            self._sicher(bild, w, ergebnis.fehler)

        for gruppe in self.panel.groups:
            screen = self._screen_waehlen(gruppe, vorwahl.get(gruppe.id), ergebnis.fehler)
            # ⚠ Gemeldet wird der SCREEN-Name, nicht die Seite: daran haengt die Stellung
            # des `select` in Home Assistant. Die Seite kommt getrennt dazu — die
            # Oberflaeche zeigt sie an, die Auswahl bleibt davon unberuehrt.
            ergebnis.aktive_screens[gruppe.id] = screen.name
            j = self._seite_waehlen(screen, seiten_vorwahl.get(gruppe.id))
            ergebnis.aktive_seiten[gruppe.id] = j
            for w in screen.seiten[j].widgets:
                self._sicher(bild, w, ergebnis.fehler)

        if notiz:
            self._benachrichtigung(bild, notiz, ergebnis)

        for meldung in ergebnis.fehler:
            if meldung not in self._gemeldet:
                self._gemeldet.add(meldung)
                _LOG.warning("%s: %s", self.panel.id, meldung)
        return ergebnis

    def _sicher(self, bild: Image.Image, w: Widget, fehler: list[str]) -> None:
        """Ein stolperndes Widget darf nie den ganzen Frame kosten."""
        try:
            self._widget(bild, w)
        except Exception as e:
            fehler.append(f"{w.pfad}: {type(e).__name__}: {e}")

    def _benachrichtigung(self, bild: Image.Image, notiz: dict,
                          ergebnis: RenderErgebnis) -> None:
        cfg = self.panel.notify
        if not cfg.region:
            return
        # Sichtbarkeitsbedingung (z.B. nur wenn jemand im Raum ist). Bei fehlerhafter
        # Vorlage lieber anzeigen als verschlucken — eine Meldung, die niemand sieht,
        # ist schlimmer als eine zu viel.
        if cfg.visible_when:
            try:
                if not self.tmpl.truthy(cfg.visible_when):
                    return
            except TemplateError as e:
                ergebnis.fehler.append(f"notify.visible_when: {e}")
        x, y, w, h = cfg.region
        text = str(notiz["text"])[: cfg.max_chars]
        bg, fg = cfg.levels.get(notiz.get("level", "info"), cfg.levels["info"])

        if len(text) > cfg.max_bar_chars:
            # Zu lang fuer einen stehenden Balken -> WLEDs eigene Laufschrift.
            # Der Bildspeicher bleibt hier schwarz; das Scroll-Segment zeichnet darueber.
            ergebnis.scroll_text = (text, bg, fg)
            return
        ImageDraw.Draw(bild).rectangle([x, y, x + w - 1, y + h - 1], fill=_hex2rgb(bg))
        self._schreibe(bild, text, x, y, w, h, fg, cfg.font)


def pixelraster(bild: "Image.Image", zoom: int) -> "Image.Image":
    """Duennes Gitter zwischen die Pixel legen — macht Abstaende zaehlbar.

    Steht hier und nicht in `web.py`, weil BEIDE Ansichten es brauchen: der Betriebs-
    Reiter und die Vorschau des Konfigurators. Lag es nur an einer Stelle, sah dasselbe
    Bild an zwei Stellen unterschiedlich aus.
    """
    from PIL import ImageDraw
    d = ImageDraw.Draw(bild)
    for x in range(0, bild.width, zoom):
        d.line([(x, 0), (x, bild.height)], fill=(24, 24, 24))
    for y in range(0, bild.height, zoom):
        d.line([(0, y), (bild.width, y)], fill=(24, 24, 24))
    return bild


#: Rastermass, auf das sich der angeforderte Zoom bezieht. P3 ist bei HUB75 die
#: gaengigste Groesse; eine P3-Matrix wird also genau mit dem angeforderten Zoom
#: gezeichnet, eine feinere kleiner und eine groebere groesser.
REFERENZ_PITCH_MM = 3.0


def led_punkte(klein: "Image.Image", zoom: int, anteil: float = 0.7) -> "Image.Image":
    """Jede LED als Punkt zeichnen statt als ausgefuelltes Quadrat.

    Naeher am echten Anblick einer HUB75-Matrix, auf der die Leuchtpunkte eben nicht
    aneinanderstossen.

    ⚠ Schwarze Pixel werden uebersprungen — nicht aus Sparsamkeit, sondern weil ein
    schwarzer Punkt auf schwarzem Grund ohnehin nichts zeichnet. Bei einem typischen Bild
    sind rund 80 % der Flaeche schwarz, das spart also den Grossteil der Aufrufe.
    """
    from PIL import Image, ImageDraw
    gross = Image.new("RGB", (klein.width * zoom, klein.height * zoom), (0, 0, 0))
    d = ImageDraw.Draw(gross)
    r = max(1, int(zoom * anteil / 2))
    px = klein.convert("RGB").load()
    for y in range(klein.height):
        for x in range(klein.width):
            farbe = px[x, y]
            if farbe == (0, 0, 0):
                continue
            cx = x * zoom + zoom // 2
            cy = y * zoom + zoom // 2
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=farbe)
    return gross


def vergroessern(klein: "Image.Image", zoom: int, pitch: float | None = None,
                 gitter: bool = True) -> tuple["Image.Image", int]:
    """Das kleine Bild auf Anzeigegroesse bringen. Rueckgabe: (Bild, benutzter Zoom).

    ★ Der GESAMTE Weg liegt hier, nicht in `web.py` und `konfigurator.py` — genau die
    Doppelung, vor der der Kommentar an `pixelraster` schon warnte. Betriebs-Reiter und
    Konfigurator muessen dasselbe Bild gleich darstellen, sonst sucht man Unterschiede,
    die es gar nicht gibt.

    `pitch` ist das Rastermass der Matrix in Millimetern (P3 = 3.0). Ist es gesetzt,
    passiert zweierlei:

    * **Massstab:** der Zoom wird darauf bezogen. Zwei Anzeigen nebeneinander stehen damit
      im echten Groessenverhaeltnis — eine P2,5 mit 64x128 ist physisch 160x320 mm und
      wird kleiner gezeichnet als eine P3 mit 128x64 (384x192 mm).
    * **Darstellung:** die LEDs werden als Punkte gezeichnet.

    Ohne `pitch` bleibt alles wie bisher — voller Zoom, duennes Gitter. Wer das Mass nicht
    eintraegt, merkt von der Aenderung also nichts.
    """
    z = zoom
    if pitch and pitch > 0:
        # ⚠ Auf ganze Zahlen runden: `Image.NEAREST` mit krummem Faktor ergibt ungleich
        # breite Pixel, und dann zaehlt man auf der Vorschau Abstaende falsch ab.
        z = max(1, round(zoom * pitch / REFERENZ_PITCH_MM))

    if pitch and pitch > 0 and z >= 4:
        return led_punkte(klein, z), z

    gross = klein.resize((klein.width * z, klein.height * z), Image.NEAREST)
    if gitter and z >= 4:
        gross = pixelraster(gross, z)
    return gross, z
