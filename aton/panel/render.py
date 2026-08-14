"""Das Bild bauen — reine Rechnerei, kein Netz.

Dieses Modul haengt weder an Home Assistant noch an WLED: es bekommt eine Zustandsquelle
(irgendetwas mit `.state()`/`.attr()`) und liefert ein Bild. Genau deshalb laesst es sich
ohne HA und ohne Matrix testen — man setzt ein dict als Quelle ein und vergleicht das
Ergebnis pixelweise.
"""
from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime

from PIL import Image, ImageDraw

from . import plugin
from .config import IconSpec, NotifyCfg, PanelCfg, TextSpec, Widget
from .const import DEFAULT_COLOR, UNAVAILABLE_STATES
from .fonts import FontRegistry
from .icons import IconRegistry, _hex2rgb
from .templates import TemplateEngine, TemplateError

_LOG = logging.getLogger(__name__)

WOCHENTAG_BALKEN_Y = 7          # Zeile des Wochentagsbalkens innerhalb der 8px-Kachel


@dataclass
class ScrollAuftrag:
    """Was WLEDs eigene Laufschrift zeichnen soll — samt der Flaeche, auf der sie steht.

    ★ Die Flaeche steht HIER und nicht mehr in `panel.notify`: seit es mehrere Meldezeilen
    geben kann, weiss nur die Zeile, die den Auftrag ausgeloest hat, wo sie liegt. Vorher
    nahm der Transport `notify.region` — mit zwei Zeilen waere die Laufschrift der zweiten
    ueber der ersten gelandet.
    """
    text: str
    bg: str
    fg: str
    region: tuple[int, int, int, int]
    speed: int = 128
    yoff: int = 128
    font: int = 128
    fx: int = 122


@dataclass
class RenderErgebnis:
    bild: Image.Image
    aktive_screens: dict[str, str] = field(default_factory=dict)
    aktive_seiten: dict[str, int] = field(default_factory=dict)
    scroll: ScrollAuftrag | None = None
    fehler: list[str] = field(default_factory=list)


class Renderer:
    def __init__(self, panel: PanelCfg, quelle, fonts: FontRegistry, icons: IconRegistry,
                 verlauf=None):
        self.panel = panel
        self.quelle = quelle
        self.fonts = fonts
        self.icons = icons
        # Optional: der Verlaufsspeicher fuer `type: sparkline`. Ohne ihn zeichnet die
        # Kurve nichts und sagt es — Vorschau, Prueflauf und Tests kommen ohne aus.
        self.verlauf = verlauf
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

    def _widget(self, bild: Image.Image, w: Widget, fehler: list[str] | None = None) -> None:
        g = self.panel.grid

        if w.bg:
            ImageDraw.Draw(bild).rectangle([w.x, w.y, w.x + w.w - 1, w.y + w.h - 1],
                                          fill=_hex2rgb(w.bg))

        if w.type == "rect":
            return

        if w.type == "icons":
            self._symbolliste(bild, w, fehler)
            return

        if w.type == "series":
            self._series(bild, w, fehler)
            return

        if w.type == "bar":
            self._balken(bild, w, fehler)
            return

        if w.type == "lines":
            self._zeilen(bild, w, fehler)
            return

        if w.type == "sparkline":
            self._kurve(bild, w, fehler)
            return

        if w.type == "image":
            self._symbol(bild, w.image, w.x, w.y)
            return

        if w.type == "calendar":
            self._kalenderblatt(bild, w)
            return

        if w.type == "clock_wd":
            self._uhr_wd(bild, w)
            return

        if w.type == "clock":
            self._uhr(bild, w)
            return

        # Eigene Typen aus /config/aton_widgets. Der Hintergrund ist oben schon gezeichnet,
        # ein Plugin bekommt `bg:` also geschenkt. Ausnahmen fangt `_sicher` ab — ein
        # fehlerhaftes Plugin hinterlaesst eine leere Stelle und eine Meldung, keinen
        # stehengebliebenen Renderer.
        eigen = plugin.registry.get(w.type)
        if eigen:
            try:
                eigen.zeichne(bild, w, plugin.Kontext(self))
            except Exception as e:
                # Der Dateiname MUSS in die Meldung: `_sicher` nennt sonst nur die Stelle
                # in der YAML, und die ist hier nicht das Problem.
                _LOG.debug("Rueckverfolgung %s", eigen.quelle, exc_info=True)
                raise RuntimeError(f"eigenes Widget {eigen.name!r} aus {eigen.quelle} — "
                                   f"{type(e).__name__}: {e}") from e
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

    def _uhr_wd(self, bild: Image.Image, w: Widget) -> None:
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

    def _uhr(self, bild: Image.Image, w: Widget) -> None:
        """Uhrzeit HH:MM."""
        jetzt = datetime.now()
        breite = w.text_w if w.text_w is not None else w.w
        feld = Image.new("RGBA", (breite, w.h), (0, 0, 0, 0))
        d = ImageDraw.Draw(feld)
        self.fonts.get(w.font).draw(d, (3, 1), jetzt.strftime("%H:%M"),
                                    _hex2rgb(self._farbe(w.color)))
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
              notiz: dict | list[dict] | None = None,
              seiten_vorwahl: dict[str, int] | None = None) -> RenderErgebnis:
        vorwahl = vorwahl or {}
        seiten_vorwahl = seiten_vorwahl or {}
        bild = Image.new("RGB", (self.panel.width, self.panel.height), (0, 0, 0))
        ergebnis = RenderErgebnis(bild=bild)

        # Erst sammeln, dann zeichnen: die Reihenfolge entscheidet, was oben liegt, und die
        # steht erst fest, wenn alle Kacheln beisammen sind (siehe `layer`).
        zu_zeichnen: list[Widget] = list(self.panel.widgets)

        for gruppe in self.panel.groups:
            screen = self._screen_waehlen(gruppe, vorwahl.get(gruppe.id), ergebnis.fehler)
            # ⚠ Gemeldet wird der SCREEN-Name, nicht die Seite: daran haengt die Stellung
            # des `select` in Home Assistant. Die Seite kommt getrennt dazu — die
            # Oberflaeche zeigt sie an, die Auswahl bleibt davon unberuehrt.
            ergebnis.aktive_screens[gruppe.id] = screen.name
            j = self._seite_waehlen(screen, seiten_vorwahl.get(gruppe.id))
            ergebnis.aktive_seiten[gruppe.id] = j
            zu_zeichnen.extend(screen.seiten[j].widgets)

        zu_zeichnen.extend(self.panel.overlays)

        # ⚠ STABIL sortieren: bei gleicher Ebene bleibt die Reihenfolge des Sammelns, also
        # erst Grundbild, dann Screens. Ohne diese Zusicherung waere eine Beschreibung ohne
        # ein einziges `layer:` schon eine andere — genau das darf ein Umbau nicht kosten.
        zu_zeichnen.sort(key=lambda w: w.layer)

        zuordnung = self._meldungen_verteilen(zu_zeichnen, notiz, ergebnis)

        for w in zu_zeichnen:
            self._sicher(bild, w, ergebnis, zuordnung.get(id(w)))

        for meldung in ergebnis.fehler:
            if meldung not in self._gemeldet:
                self._gemeldet.add(meldung)
                _LOG.warning("%s: %s", self.panel.id, meldung)
        return ergebnis

    def _sicher(self, bild: Image.Image, w: Widget, ergebnis: RenderErgebnis,
                notiz: dict | None = None) -> None:
        """Ein stolperndes Widget darf nie den ganzen Frame kosten."""
        try:
            if w.visible_when:
                # Bei fehlerhafter Vorlage lieber zeichnen als verschlucken — eine Kachel,
                # die wegen eines Tippfehlers in der Bedingung fehlt, sucht man im Bild.
                try:
                    if not self.tmpl.truthy(w.visible_when):
                        return
                except TemplateError as e:
                    ergebnis.fehler.append(f"{w.pfad}.visible_when: {e}")
            if w.type == "notify":
                self._meldezeile(bild, w, notiz, ergebnis)
                return
            self._widget(bild, w, ergebnis.fehler)
        except Exception as e:
            ergebnis.fehler.append(f"{w.pfad}: {type(e).__name__}: {e}")

    def _symbolliste(self, bild: Image.Image, w: Widget,
                     fehler: list[str] | None = None) -> None:
        """Eine Liste von Symbolen im Bereich der Kachel — mit Umbruch.

        Die Namen kommen aus der TEXTQUELLE (`template`, `value` oder `text`), getrennt
        durch Komma oder Leerzeichen. Damit braucht dieser Typ keinen eigenen Schluessel
        und kann alles, was Text auch kann — vor allem Jinja.

        ★ Gleichmaessige Zellen: die Spaltenbreite ist fuer ALLE Symbole gleich (das
        breiteste vorkommende, oder `cell_size`). Symbole sind unterschiedlich breit
        (`builtin_icons.BREITEN`); wer sie einfach aneinanderreiht, bekommt eine Reihe,
        die in der zweiten Zeile nicht mehr untereinander steht. Innerhalb seiner Zelle
        wird jedes Symbol zentriert.

        ⚠ Ein unbekannter Name wirft NICHT den ganzen Frame weg: er wird uebersprungen
        und gemeldet. `self.icons.get` wuerde sonst mit KeyError aussteigen und die ganze
        Kachel kosten — bei einer Liste aus einer Vorlage ist ein Tippfehler in EINEM
        Namen aber der Normalfall.
        """
        if not w.text:
            return
        roh = self._text(w.text)
        namen = [t for t in re.split(r"[,\s]+", roh.strip()) if t]
        if not namen:
            return

        bilder, unbekannt = [], []
        for n in namen:
            try:
                bilder.append((n, self.icons.get(n)))
            except KeyError:
                unbekannt.append(n)
        if unbekannt and fehler is not None:
            fehler.append(f"{w.pfad}: Symbol(e) nicht gefunden: {', '.join(unbekannt)}")
        if not bilder:
            return

        zelle_b = w.cell_w if w.cell_w else max(b.width for _, b in bilder)
        zelle_h = w.cell_h if w.cell_h else max(b.height for _, b in bilder)
        schritt_x = zelle_b + w.spacing
        schritt_y = zelle_h + (w.spacing if w.line_spacing is None else w.line_spacing)
        je_zeile = max(1, (w.w + w.spacing) // schritt_x)

        # Zeilenweise aufteilen, damit die letzte Zeile mit ausgerichtet werden kann.
        zeilen = [bilder[i:i + je_zeile] for i in range(0, len(bilder), je_zeile)]
        passt = max(1, (w.h + w.spacing) // schritt_y)
        if len(zeilen) > passt:
            if fehler is not None:
                fehler.append(f"{w.pfad}: {len(bilder)} Symbole passen nicht in "
                              f"{w.w}x{w.h} — {sum(len(z) for z in zeilen[passt:])} "
                              "abgeschnitten")
            zeilen = zeilen[:passt]

        for zi, zeile in enumerate(zeilen):
            breite = len(zeile) * schritt_x - w.spacing
            if w.align == "center":
                x0 = w.x + (w.w - breite) // 2
            elif w.align == "right":
                x0 = w.x + w.w - breite
            else:
                x0 = w.x
            y0 = w.y + zi * schritt_y
            for si, (_, sym) in enumerate(zeile):
                # In der Zelle zentrieren — sonst „klebt" ein schmales Symbol links.
                x = x0 + si * schritt_x + (zelle_b - sym.width) // 2
                y = y0 + (zelle_h - sym.height) // 2
                bild.paste(sym, (x, y), sym)

    def _wert(self, w: Widget) -> float | None:
        """Der Zahlenwert einer Kachel — aus `value` direkt, sonst aus dem gerenderten Text.

        ⚠ Ueber `value` wird die ENTITAET gelesen, nicht ihr formatierter Text: `format`
        oder `decimals` wuerden sonst mitrechnen, und aus `21,5 °C` liesse sich keine Zahl
        mehr gewinnen (Komma, Einheit). Nur wenn keine Entitaet dasteht — also bei einer
        Vorlage — wird der gerenderte Text als Zahl gelesen.
        """
        eid = getattr(w.text, "value", None)
        if eid:
            return self._zahl(eid, getattr(w.text, "attribute", None))
        try:
            return float(str(self._text(w.text)).strip().replace(",", "."))
        except (TypeError, ValueError):
            return None

    def _balken(self, bild: Image.Image, w: Widget,
                fehler: list[str] | None = None) -> None:
        """Fuellstandsbalken zwischen `min` und `max`.

        War bis 0.20.2 nur ein Beispiel-Plugin (`examples/widgets/bargraph.py`) und ist
        jetzt eingebaut — Batterie, Zisterne, Autarkie, Restzeit sind zu haeufig, um dafuer
        `custom_widgets: true` zu verlangen (das Verzeichnis fuehrt Code aus und ist
        deshalb aus gutem Grund aus).

        ★ Die Farbe kommt aus der GEWOEHNLICHEN Farbquelle der Kachel. Damit faerbt
        `steps:` den Balken nach Schwellen, ohne dass dieser Typ etwas Eigenes dafuer
        braucht — eine Batterie unter 20 % wird rot, weil das an jeder Kachel so geht.
        """
        von = 0.0 if w.skala_min is None else w.skala_min
        bis = 100.0 if w.skala_max is None else w.skala_max
        d = ImageDraw.Draw(bild)

        if w.track:
            d.rectangle([w.x, w.y, w.x + w.w - 1, w.y + w.h - 1], fill=_hex2rgb(w.track))

        wert = self._wert(w)
        if wert is None:
            # ⚠ Kein Balken bei 0 %: `unknown` heisst „ich weiss es nicht", nicht „leer".
            # Ein Balken auf null waere eine Aussage, die der Sensor nie gemacht hat.
            if fehler is not None:
                fehler.append(f"{w.pfad}: kein Zahlenwert fuer den Balken")
            return
        if bis == von:
            if fehler is not None:
                fehler.append(f"{w.pfad}: min und max sind gleich ({von})")
            return

        anteil = min(1.0, max(0.0, (wert - von) / (bis - von)))
        farbe = _hex2rgb(self._farbe(w.color))
        if w.vertical:
            hoch = round(w.h * anteil)
            if hoch:
                d.rectangle([w.x, w.y + w.h - hoch, w.x + w.w - 1, w.y + w.h - 1],
                            fill=farbe)
        else:
            breit = round(w.w * anteil)
            if breit:
                d.rectangle([w.x, w.y, w.x + breit - 1, w.y + w.h - 1], fill=farbe)

    def _zeilen(self, bild: Image.Image, w: Widget,
                fehler: list[str] | None = None) -> None:
        """Mehrere Textzeilen aus einer Quelle — Aufgaben, Termine, Einkaufszettel.

        `series` macht SPALTEN, `icons` macht SYMBOLE — Textzeilen gab es bis 0.20.2
        nicht, und wer eine Liste zeigen wollte, baute je Zeile eine eigene Kachel mit von
        Hand gerechnetem `at:`. Beim Einfuegen einer Zeile rutschte dann alles.

        ★ Ein `@name ` am Zeilenanfang ist ein SYMBOL — dieselbe Schreibweise wie bei
        `series`. Zwei Konventionen fuer dasselbe waeren eine zu viel.

        ⚠ Zu lange Zeilen werden gekuerzt, nicht umgebrochen: auf 64 px passen je nach
        Schrift acht bis zwoelf Zeichen, ein Umbruch machte aus drei Aufgaben eine. Dass
        gekuerzt wurde, sagt die Kachel im Betriebs-Reiter.
        """
        roh = str(self._text(w.text) or "")
        trenner = w.separator if w.separator else "\n"
        zeilen = [z.strip() for z in roh.split(trenner) if z.strip()]
        if not zeilen:
            return

        font = self.fonts.get(w.font)
        zeilen_h = font.measure("0")[1]
        abstand = w.spacing if w.line_spacing is None else w.line_spacing
        schritt = zeilen_h + abstand
        passt = max(1, (w.h + abstand) // schritt) if schritt else 1
        hoechstens = min(passt, w.max_rows) if w.max_rows else passt

        if len(zeilen) > hoechstens and fehler is not None:
            fehler.append(f"{w.pfad}: {len(zeilen)} Zeilen, {hoechstens} passen — "
                          f"{len(zeilen) - hoechstens} weggelassen")
        farbe = self._farbe(w.color)
        unbekannt: list[str] = []

        for i, zeile in enumerate(zeilen[:hoechstens]):
            y = w.y + i * schritt
            x, breite = w.x, w.w
            if zeile.startswith("@"):
                name, _, rest = zeile[1:].partition(" ")
                try:
                    symbol = self.icons.get(name.strip())
                    bild.paste(symbol, (x, y), symbol)
                    versatz = symbol.width + self.panel.grid.gap
                    x += versatz
                    breite -= versatz
                except KeyError:
                    unbekannt.append(name.strip())
                zeile = rest.strip()
            if zeile:
                self._schreibe(bild, self._kuerzen(zeile, font, breite), x, y,
                               breite, zeilen_h + 2, farbe, w.font, w.align)

        if unbekannt and fehler is not None:
            fehler.append(f"{w.pfad}: Symbol(e) nicht gefunden: {', '.join(unbekannt)}")

    def _kuerzen(self, text: str, font, breite: int) -> str:
        """So weit kuerzen, dass es in `breite` passt. Ohne Ellipse — dafuer ist kein Platz.

        ⚠ Zeichenweise messen statt zu schaetzen: die eingebaute 5x3 ist proportional
        genug, dass `breite // 4` mal zu kurz und mal zu lang liegt.
        """
        if font.measure(text)[0] <= breite:
            return text
        for n in range(len(text) - 1, 0, -1):
            if font.measure(text[:n])[0] <= breite:
                return text[:n]
        return ""

    def _kurve(self, bild: Image.Image, w: Widget,
               fehler: list[str] | None = None) -> None:
        """Der Verlauf einer Entitaet als Linie — die einzige Kachel, die zurueckblickt.

        ★★ Die Daten kommen NICHT aus dem Zustandsspiegel, sondern aus HAs Recorder, und
        zwar aus dem Verlaufsspeicher (`panel/verlauf.py`), den eine Hintergrundaufgabe
        frisch haelt. Hier wird nur gelesen — `frame()` ist synchron und laeuft 720-mal
        pro Stunde, eine Recorder-Abfrage hat darin nichts verloren.

        ⚠ Ohne Daten wird NICHTS gezeichnet und der Grund gemeldet. Eine Linie auf der
        Grundlinie saehe aus wie „der Wert war die ganze Zeit null".
        """
        eid = getattr(w.text, "value", "")
        werte = self.verlauf.punkte(eid, w.hours) if self.verlauf else []
        if len(werte) < 2:
            if fehler is not None:
                grund = (self.verlauf.fehler(eid, w.hours) if self.verlauf
                         else "kein Verlaufsspeicher")
                fehler.append(f"{w.pfad}: kein Verlauf fuer {eid} "
                              f"({grund or 'noch nicht geholt'})")
            return

        # ★ Ohne feste Skala die Spanne der Daten nehmen. Bei einer Aussentemperatur um
        # 20 °C waere eine Skala ab 0 eine waagerechte Linie ganz oben — sichtbar waere
        # genau nichts. Ein Mindestabstand verhindert die Division durch (fast) null,
        # wenn der Wert ueber Stunden konstant war.
        von = min(werte) if w.skala_min is None else w.skala_min
        bis = max(werte) if w.skala_max is None else w.skala_max
        if bis - von < 1e-9:
            von, bis = von - 0.5, bis + 0.5

        d = ImageDraw.Draw(bild)
        n = len(werte)
        unten, hoehe = w.y + w.h - 1, w.h - 1

        def punkt(i: int, v: float) -> tuple[int, int]:
            x = w.x + (i * (w.w - 1) // (n - 1))
            anteil = min(1.0, max(0.0, (v - von) / (bis - von)))
            return x, unten - round(hoehe * anteil)

        punkte = [punkt(i, v) for i, v in enumerate(werte)]

        if w.fill:
            # Flaeche als Polygon bis zur Grundlinie — sonst haette die Fuellung Loecher,
            # wo die Kurve steil faellt.
            d.polygon([(w.x, unten)] + punkte + [(w.x + w.w - 1, unten)],
                      fill=_hex2rgb(w.fill))
        d.line(punkte, fill=_hex2rgb(self._farbe(w.color)))

    def _series(self, bild: Image.Image, w: Widget,
                fehler: list[str] | None = None) -> None:
        """Spalten mit frei gewaehlten Reihen — Text und Symbole gemischt.

        Eine Zeile aus der Textquelle. Spalten durch Komma, die Reihen einer Spalte durch
        `|`. Ein Teil mit `@` davor ist ein SYMBOL, alles andere ist Text:

            14|@w_sun|21°     Text, Symbol, Text (Stundenvorhersage)
            Mo|Di             zwei Textreihen
            @w_sun|@w_rain    zwei Symbolreihen
            @r_liv|22°        Symbol ueber Text
            @r_liv            nur ein Symbol

        ★ Warum `@` und keine automatische Erkennung: ohne Kennzeichen muesste der Renderer
        raten, ob `info` der Text „info" oder das Symbol `info` ist. Schlimmer noch — ein
        neu gezeichnetes Symbol wuerde bestehende Kacheln stillschweigend veraendern, weil
        ein bisheriger Text ploetzlich als Symbolname durchgeht.

        ★ Die Reihen sind gleich hoch ueber ALLE Spalten (je Reihe das hoechste Vorkommen),
        die Zellen gleich breit. Nur so stehen die Spalten buendig, auch wenn eine
        Beschriftung doppelt so breit ist wie ihre Nachbarn.
        """
        if not w.text:
            return
        eintraege = [t.strip() for t in self._text(w.text).split(",") if t.strip()]
        if not eintraege:
            return

        font = self.fonts.get(w.font)
        farbe = self._farbe(w.color)
        text_h = font.measure("0")[1]

        def reihen_schrift(i: int):
            """Schrift der Reihe i — oder die der Kachel.

            ⚠ Eine unbekannte Schrift kostet nicht die Kachel: `fonts.get` wirft, und
            ohne diesen Fang waere der ganze Frame an dieser Stelle weg. Gemeldet wird
            trotzdem, sonst sucht man den Grund fuer die falsche Schrift im Bild.
            """
            name = w.row_fonts[i] if i < len(w.row_fonts) else ""
            if not name:
                return font
            try:
                return self.fonts.get(name)
            except KeyError:
                if fehler is not None:
                    hinweis = f"{w.pfad}: Schrift {name!r} nicht gefunden (Reihe {i + 1})"
                    if hinweis not in fehler:
                        fehler.append(hinweis)
                return font

        def reihen_farbe(i: int) -> str:
            wert = w.row_colors[i] if i < len(w.row_colors) else ""
            return wert or farbe

        # Je Spalte eine Liste von Reihen: ("sym", Bild) oder ("text", Zeichenkette)
        spalten: list[list[tuple[str, object]]] = []
        unbekannt: list[str] = []
        for e in eintraege:
            reihen: list[tuple[str, object]] = []
            for teil in e.split("|"):
                teil = teil.strip()
                if teil.startswith("@"):
                    name = teil[1:].strip()
                    if not name:
                        continue
                    try:
                        reihen.append(("sym", self.icons.get(name)))
                    except KeyError:
                        unbekannt.append(name)
                        reihen.append(("text", ""))    # Platz halten, damit die Reihen
                                                       # der Nachbarspalten nicht rutschen
                else:
                    reihen.append(("text", teil))
            spalten.append(reihen)
        if unbekannt and fehler is not None:
            fehler.append(f"{w.pfad}: Symbol(e) nicht gefunden: {', '.join(unbekannt)}")

        anzahl_reihen = max(len(sp) for sp in spalten)
        if not anzahl_reihen:
            return

        # Hoehe je REIHE ueber alle Spalten hinweg — sonst stuenden gemischte Spalten
        # (Symbol hier, Text dort) auf verschiedenen Grundlinien.
        reihen_h = []
        for i in range(anzahl_reihen):
            # ⚠ Die Hoehe einer Textreihe richtet sich nach IHRER Schrift — eine groessere
            # Schrift in Reihe 3 braucht mehr Platz, sonst ueberlappt sie die Nachbarreihe.
            hoch = 0
            for sp in spalten:
                if i < len(sp):
                    art, wert = sp[i]
                    hoch = max(hoch, wert.height if art == "sym"
                               else reihen_schrift(i).measure("0")[1])
            reihen_h.append(hoch)

        zeilen_abstand = w.spacing if w.line_spacing is None else w.line_spacing
        block_h = sum(reihen_h) + zeilen_abstand * (anzahl_reihen - 1)
        block_h = w.cell_h if w.cell_h else block_h

        breiten = []
        for sp in spalten:
            b = 0
            for i, (art, wert) in enumerate(sp):
                b = max(b, wert.width if art == "sym"
                        else (reihen_schrift(i).measure(wert)[0] if wert else 0))
            breiten.append(b)
        zelle_b = w.cell_w if w.cell_w else max(breiten)

        schritt_x = zelle_b + w.spacing
        je_zeile = max(1, (w.w + w.spacing) // schritt_x)
        zeilen = [spalten[i:i + je_zeile] for i in range(0, len(spalten), je_zeile)]
        passt = max(1, (w.h + zeilen_abstand) // (block_h + zeilen_abstand))
        if len(zeilen) > passt:
            if fehler is not None:
                fehler.append(f"{w.pfad}: {len(spalten)} Spalten passen nicht in "
                              f"{w.w}x{w.h} — {sum(len(z) for z in zeilen[passt:])} "
                              "abgeschnitten")
            zeilen = zeilen[:passt]

        for zi, zeile in enumerate(zeilen):
            breite = len(zeile) * schritt_x - w.spacing
            if w.align == "center":
                x0 = w.x + (w.w - breite) // 2
            elif w.align == "right":
                x0 = w.x + w.w - breite
            else:
                x0 = w.x
            y_block = w.y + zi * (block_h + zeilen_abstand)

            for si, sp in enumerate(zeile):
                zx = x0 + si * schritt_x
                y = y_block
                for i in range(anzahl_reihen):
                    h = reihen_h[i]
                    if i < len(sp):
                        art, wert = sp[i]
                        if art == "sym":
                            bild.paste(wert, (zx + (zelle_b - wert.width) // 2,
                                              y + (h - wert.height) // 2), wert)
                        elif wert:
                            # ⚠ `y - 1`: `_schreibe` rueckt seinen Text im Feld um 1 px
                            # nach unten. Ohne die Korrektur sind die Abstaende ueber und
                            # unter einer Reihe verschieden (0.16.1).
                            r_font = w.row_fonts[i] if i < len(w.row_fonts) else ""
                            self._schreibe(bild, wert, zx, y - 1, zelle_b, h + 2,
                                           reihen_farbe(i), r_font or w.font, "center")
                    y += h + zeilen_abstand

    # ==================================================================
    #  Meldungen
    # ==================================================================
    def _meldungen_verteilen(self, zu_zeichnen: list[Widget],
                             notiz: dict | list[dict] | None,
                             ergebnis: RenderErgebnis) -> dict[int, dict]:
        """Welche Meldung steht in welcher Zeile?

        Zwei Regeln, und die zweite ist die wichtigere:

        · Eine Zeile mit `channel: x` zeigt ausschliesslich Meldungen dieses Kanals.
        · Eine Zeile OHNE Kanal ist die Hauptzeile. Sie zeigt alles Kanallose — und
          zusaetzlich Meldungen, fuer deren Kanal es auf dieser Anzeige gar keine Zeile
          gibt. Sonst verschwaende ein Tippfehler im Kanal die Meldung spurlos, und der
          Dienst haette „ok" gemeldet.

        Was gar nirgends unterkommt, wird als Fehler vermerkt — sichtbar in der
        Oberflaeche, solange die Meldung laeuft.
        """
        notizen = [notiz] if isinstance(notiz, dict) else list(notiz or [])
        zeilen = [w for w in zu_zeichnen if w.type == "notify"]
        # ⚠ Eine Anzeige GANZ OHNE Meldezeile schweigt — sie ist kein Fehler. `aton.notify`
        # ohne `panel:` geht ausdruecklich an alle Anzeigen, und die kleine 32x16 am
        # Eingang hat keine Zeile und braucht keine. Beim Vergleich mit der laufenden
        # Beschreibung stand hier sonst auf zwei von drei Anzeigen dauerhaft eine rote
        # Zeile — fuer etwas, das genau so gemeint ist.
        if not notizen or not zeilen:
            return {}

        kanaele = {w.notify.channel for w in zeilen if w.notify and w.notify.channel}
        zuordnung: dict[int, dict] = {}
        untergekommen: set[int] = set()

        for w in zeilen:
            cfg = w.notify or NotifyCfg()
            for i, n in enumerate(notizen):
                if _passt(cfg, n, kanaele):
                    zuordnung[id(w)] = n
                    untergekommen.add(i)
                    break

        for i, n in enumerate(notizen):
            if i not in untergekommen:
                ergebnis.fehler.append(
                    f"Meldung {str(n.get('text', ''))[:40]!r} (Kanal "
                    f"{n.get('channel') or '—'}, Stufe {n.get('level', 'info')}): "
                    "keine passende Meldezeile")
        return zuordnung

    def _meldezeile(self, bild: Image.Image, w: Widget, notiz: dict | None,
                    ergebnis: RenderErgebnis) -> None:
        """Eine Meldezeile zeichnen. Ohne Meldung bleibt sie leer — nicht schwarz.

        ⚠ Kein `bg` fuer die leere Zeile: `_widget` fuellt einen gesetzten Hintergrund
        sonst auch dann, wenn nichts anliegt, und dann steht auf der Matrix ein Balken
        ohne Inhalt. Die Farbe kommt aus der STUFE der Meldung.
        """
        cfg = w.notify or NotifyCfg()
        if not notiz:
            return
        text = str(notiz.get("text", ""))[: cfg.max_chars]
        if not text:
            return
        bg, fg = cfg.levels.get(str(notiz.get("level", "info")),
                                cfg.levels.get("info", ("00c000", "ffffff")))

        if len(text) > cfg.max_bar_chars:
            # Zu lang fuer einen stehenden Balken -> WLEDs eigene Laufschrift.
            # Der Bildspeicher bleibt hier schwarz; das Scroll-Segment zeichnet darueber.
            #
            # ⚠ Es gibt nur EIN Scroll-Segment je Geraet (`panel.scroll_segment`). Die
            # zweite laufende Meldung kann also nicht auch noch laufen — das gehoert
            # gesagt und nicht verschluckt.
            if ergebnis.scroll is None:
                ergebnis.scroll = ScrollAuftrag(
                    text=text, bg=bg, fg=fg, region=(w.x, w.y, w.w, w.h),
                    speed=cfg.scroll_speed, yoff=cfg.scroll_yoff, font=cfg.scroll_font,
                    fx=cfg.scroll_fx)
            else:
                ergebnis.fehler.append(
                    f"{w.pfad}: zweite Laufschrift gleichzeitig — das Geraet hat nur ein "
                    f"Scroll-Segment. Kuerzer als max_bar_chars ({cfg.max_bar_chars}) "
                    "bliebe die Meldung ein stehender Balken")
            return
        ImageDraw.Draw(bild).rectangle([w.x, w.y, w.x + w.w - 1, w.y + w.h - 1],
                                       fill=_hex2rgb(bg))
        self._schreibe(bild, text, w.x, w.y, w.w, w.h, fg, cfg.font, w.align)


def _passt(cfg: NotifyCfg, notiz: dict, kanaele: set[str]) -> bool:
    """Gehoert diese Meldung in diese Zeile? Regeln siehe `_meldungen_verteilen`."""
    if cfg.show_levels and str(notiz.get("level", "info")) not in cfg.show_levels:
        return False
    kanal = notiz.get("channel")
    if cfg.channel:
        return kanal == cfg.channel
    return not kanal or kanal not in kanaele


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
