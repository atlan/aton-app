"""Eine Anzeige betreiben: Takt, Tor, Screens, Benachrichtigungen, Bedienelemente."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

import aiohttp

from .config import PanelCfg
from .const import AUTOMATIK
from .fonts import FontRegistry
from .hass import HomeAssistant
from .icons import IconRegistry
from .render import RenderErgebnis, Renderer
from .wled import WledTransport

_LOG = logging.getLogger(__name__)

#: Wie lange nach dem Einschalten Sendefehler als „faehrt hoch" durchgehen, statt als
#: roter Kasten zu erscheinen. Gemessen am 02.08.2026: zwischen „Strom an" und „WLED im
#: Netz" lagen 20 Sekunden. 60 gibt Luft und bleibt kurz genug, dass ein Geraet, das gar
#: nicht hochkommt, zeitnah wieder ehrlich meckert.
HOCHLAUF_S = 60.0

#: Wie lange auf ein `on` der Tor-Entitaet gewartet wird, bevor trotzdem gesendet wird.
#:
#: ★★ Das Tor IST der Erreichbarkeitsmelder — HAs WLED-Anbindung setzt es erst auf `on`,
#: wenn sie mit dem Geraet spricht. Am 14.08.2026 an beiden Wohnzimmer-Matrizen gemessen:
#:
#:     Strom `switch.matrix_relay` on   11:21:18,33
#:     Tor   `light.matrix_power`   11:21:38,59      →  20,3 s spaeter
#:     Strom `switch.matrix_tv_relay`   on   10:43:20,08
#:     Tor   `…_matrix_tv_power`      on   10:43:38,01      →  17,9 s spaeter
#:
#: Die App startete bisher auf der Sekunde des STROMSCHALTERS (ueber `gate.fallback`) und
#: schickte 20 Sekunden lang Vollbilder ins Leere. Der Rueckfall war als NOTAUSGANG
#: gedacht (ohne zweites Segment legt HA den Hauptschalter nicht an — siehe
#: `freigegeben()`), wurde aber als BESCHLEUNIGER benutzt und hat den Melder ueberholt.
#:
#: ⚠ 90 s waren aus einer Stichprobe von ZWEI gewaehlt. Beim Nachweis am selben Tag hat
#: dieselbe Anzeige **95 s** gebraucht (Skript: 20 s feste Wartezeit + HAs Einrichtung des
#: Konfigurationseintrags). Zu knapp ist billig — es kostet eine Probe, dann greift der
#: Rueckzug —, aber deshalb ist der Wert je Anzeige einstellbar (`gate.wartezeit`).
#: Dies hier ist nur die Vorgabe.
NOTAUSGANG_S = 90.0

#: Obergrenze des Rueckzugs nach einem gescheiterten Sendeversuch. Ohne ihn hat die App
#: am 14.08.2026 eine stromlose Matrix 7,5 Stunden lang im 5-Sekunden-Takt angerufen.
RUECKZUG_MAX_S = 60.0


@dataclass
class Notiz:
    text: str
    level: str = "info"
    bis: float | None = None
    prio: int = 1
    lfd: int = 0
    # In welche Meldezeile sie gehoert. None = Hauptzeile (jede Zeile ohne eigenen Kanal).
    channel: str | None = None


class Display:
    def __init__(self, panel: PanelCfg, ha: HomeAssistant,
                 fonts: FontRegistry, icons: IconRegistry):
        self.cfg = panel
        self.ha = ha
        self.renderer = Renderer(panel, ha, fonts, icons)
        self.transport = WledTransport(panel)

        self._lock = asyncio.Lock()
        self._sofort = asyncio.Event()
        self._vorwahl: dict[str, str | None] = {g.id: None for g in panel.groups}
        self._notizen: dict[str, Notiz] = {}
        self._lfd = 0
        self._eigene_helligkeit = panel.brightness_default
        # Zuletzt selbst gesetzte Helligkeit + Verfallszeit — siehe `helligkeit()`.
        self._gesetzte_helligkeit: tuple[int | None, float] = (None, 0.0)
        self.letztes_ergebnis: RenderErgebnis | None = None
        self.letzter_lauf: float = 0.0
        # Einmal gerechnetes Bild fuer eine Anzeige, die seit dem Start nie lief —
        # siehe `vorschaubild()`.
        self._kaltes_bild = None
        # War die Anzeige beim vorigen Takt freigegeben? Der Wechsel aus/ein erzwingt ein
        # Vollbild. Startwert False: beim allerersten Takt weiss die App ohnehin nicht,
        # was auf dem Geraet steht — also gleich die ganze Flaeche beschreiben.
        self._war_frei = False
        # Wann wurde zuletzt eingeschaltet? Bezugspunkt fuer die Hochlauf-Nachsicht.
        self._frei_seit = 0.0
        # Seit wann meldet die Tor-Entitaet kein `on`? 0 = sie meldet es. Bezugspunkt
        # fuer den Notausgang.
        self._tor_nicht_on_seit = 0.0
        # Fruehester naechster Sendeversuch (Unix-Zeit) und die aktuelle Rueckzugsdauer.
        self._naechster_versuch = 0.0
        self._rueckzug = 0.0
        # Warum gerade nicht gesendet wird — Klartext fuer die Oberflaeche. Leer = es
        # wird gesendet.
        self.sendepause = ""

    # ==================================================================
    #  Anmeldung
    # ==================================================================
    def starte_beobachtung(self) -> None:
        """Tor-Wechsel sollen nicht bis zum naechsten Takt warten.

        Bedienelemente in Home Assistant legt die App NICHT selbst an — das macht die
        Begleit-Integration ueber die HTTP-Schnittstelle. Die App bleibt damit frei von
        MQTT und laeuft auch dort, wo es keinen Broker gibt.
        """
        p = self.cfg
        wach = {e for e in (p.gate_entity, p.gate_fallback, p.brightness_entity) if e}
        if wach:
            self.ha.bei_aenderung(lambda eid: self._sofort.set() if eid in wach else None)

    # -- Befehle -----------------------------------------------------------
    def waehle(self, gruppen_id: str, wert: str) -> None:
        wert = wert.strip()
        gruppe = next((g for g in self.cfg.groups if g.id == gruppen_id), None)
        if gruppe is None:
            return
        if wert != AUTOMATIK and wert not in [s.name for s in gruppe.screens]:
            _LOG.warning("%s/%s: unbekannte Stellung %r", self.cfg.id, gruppen_id, wert)
            return
        self._vorwahl[gruppen_id] = None if wert == AUTOMATIK else wert
        self._sofort.set()

    def vollbild_erzwingen(self) -> None:
        self.transport.vollbild_erzwingen()
        self._sofort.set()

    async def setze_helligkeit(self, wert) -> int | None:
        """Helligkeit setzen — dorthin, wo sie auch GELESEN wird.

        Rueckgabe: der tatsaechlich gesetzte Wert (nach Begrenzung auf 1..255), oder
        None, wenn es nicht ging. Vorher war es ein blosses `True`, und der Aufrufer
        musste den Wert selbst zurueckholen — genau dabei bekam er den alten.

        ⚠ Vorher schrieb das nur `_eigene_helligkeit`. Den Wert liest `helligkeit()` aber
        ausschliesslich, wenn KEINE `brightness.entity` konfiguriert ist — bei einer
        konfigurierten Entitaet war der Regler also wirkungslos, ohne dass irgendwo etwas
        schiefging: Der Schieber bewegte sich, die Matrix blieb wie sie war, und beim
        naechsten Takt sprang der Regler auf den alten Wert zurueck.
        """
        try:
            neu = max(1, min(255, int(float(wert))))
        except (TypeError, ValueError):
            return None

        eid = self.cfg.brightness_entity
        if eid:
            domain = eid.split(".", 1)[0]
            if domain in ("input_number", "number"):
                ok = await self.ha.rufe_dienst(eid, "set_value", {"value": neu})
            else:
                # Andere Domains koennen wir nicht sinnvoll setzen — dann wenigstens
                # nicht so tun, als haette es geklappt.
                _LOG.warning("%s: Helligkeit ueber %s nicht setzbar (Domain %s)",
                             self.cfg.id, eid, domain)
                return None
            if not ok:
                return None
            # 10 s Vorrang, bis HAs Zustandsspiegel nachgezogen hat — siehe `helligkeit()`.
            self._gesetzte_helligkeit = (neu, time.monotonic() + 10.0)
            self._sofort.set()
            return neu

        self._eigene_helligkeit = neu
        self._sofort.set()
        return neu

    def notiz_setzen(self, d: dict) -> str:
        """Meldung anzeigen. Rueckgabe: die Kennung, unter der sie gefuehrt wird."""
        if not isinstance(d, dict):
            d = {"text": str(d)}

        # ⚠ Ein vorhandener Schluessel mit dem Wert null ist NICHT dasselbe wie ein
        # fehlender: `d.get("duration", 30)` liefert dann None, und `None or 0` waere 0
        # — also eine Meldung ohne Ablauf, die ewig stehenbliebe. Genau so verschickt es
        # eine Vorlage, die ein leeres Feld mitsendet. Deshalb null wie fehlend behandeln.
        d = {k: v for k, v in d.items() if v is not None}

        self._lfd += 1
        nid = str(d.get("id") or f"n{self._lfd}")
        level = str(d.get("level", "info")).lower()
        # ⚠ Gegen die Stufen ALLER Meldezeilen geprueft, nicht gegen eine einzelne: seit
        # 0.13.0 darf jede Zeile eigene Stufen mitbringen, und eine Meldung fuer die zweite
        # Zeile faende sich sonst stillschweigend auf `info` zurueckgesetzt.
        if level not in self.cfg.notify_levels:
            level = "info"

        try:
            dauer = float(d.get("duration", 30))
        except (TypeError, ValueError):
            dauer = 30.0
        try:
            prio = int(d.get("priority", 2 if level == "warning" else 1))
        except (TypeError, ValueError):
            prio = 2 if level == "warning" else 1

        kanal = d.get("channel")
        self._notizen[nid] = Notiz(
            text=str(d.get("text", "")),
            level=level,
            bis=(time.time() + dauer) if dauer > 0 else None,
            prio=prio,
            lfd=self._lfd,
            channel=(str(kanal).strip() or None) if kanal else None,
        )
        self._sofort.set()
        return nid

    def notiz_loeschen(self, nid: str | None = None, channel: str | None = None) -> None:
        """Eine Meldung loeschen — nach Kennung, nach Kanal, ohne beides alle."""
        if nid:
            self._notizen.pop(str(nid), None)
        elif channel:
            for k, n in list(self._notizen.items()):
                if n.channel == channel:
                    del self._notizen[k]
        else:
            self._notizen.clear()
        self._sofort.set()

    def _aktive_notizen(self) -> list[dict]:
        """Alle laufenden Meldungen, die dringendste zuerst.

        ⚠ Nicht mehr nur die eine beste: mit mehreren Meldezeilen entscheidet erst der
        Renderer, welche Meldung wohin gehoert — eine Warnung in der Warnzeile UND eine
        Information in der Hauptzeile sind seit 0.13.0 gleichzeitig moeglich. Waehlte diese
        Stelle weiterhin vor, bliebe die zweite Zeile fuer immer leer.
        """
        jetzt = time.time()
        for nid, n in list(self._notizen.items()):
            if n.bis is not None and n.bis <= jetzt:
                del self._notizen[nid]
        sortiert = sorted(self._notizen.values(), key=lambda n: (n.prio, n.lfd), reverse=True)
        return [{"text": n.text, "level": n.level, "channel": n.channel} for n in sortiert]

    def _aktive_notiz(self) -> dict | None:
        alle = self._aktive_notizen()
        return alle[0] if alle else None

    @property
    def vorwahl(self) -> dict[str, str | None]:
        """Handauswahl je Screen-Gruppe; None = Automatik."""
        return dict(self._vorwahl)

    def aktive_notiz(self) -> dict | None:
        """Die dringendste Meldung — fuer die Zustandsanzeige der Oberflaeche."""
        return self._aktive_notiz()

    def aktive_notizen(self) -> list[dict]:
        return self._aktive_notizen()

    def vorschaubild(self):
        """Das Bild fuer die Betriebsansicht — was zuletzt GERECHNET wurde.

        ★★ Solange die Anzeige laeuft, ist das schlicht `letztes_ergebnis`. Ist sie aus,
        hat der Takt nie gerechnet, und frueher rechnete dieser Endpunkt bei JEDEM Abruf
        neu — die Betriebsansicht pollt alle 3 s, und weil im Bild Uhr und Live-Werte
        stehen, aenderte sich die Vorschau einer ABGESCHALTETEN Matrix munter weiter.

        ⚠ Das trat nur auf, wenn die Anzeige seit dem Start der App noch nie gelaufen
        war — danach steht ja ein Ergebnis bereit und die Vorschau steht still. Genau
        daher das „manchmal" in der Meldung des Users (14.08.2026).

        Jetzt wird das kalte Bild EINMAL gerechnet und behalten. Es bleibt getrennt von
        `letztes_ergebnis`, damit `letzter_lauf` und die Screen-Anzeige nicht behaupten,
        es habe ein Takt stattgefunden.
        """
        if self.letztes_ergebnis is not None:
            self._kaltes_bild = None
            return self.letztes_ergebnis.bild
        if self._kaltes_bild is None:
            self._kaltes_bild = self.renderer.frame(self.vorwahl, self.aktive_notizen()).bild
        return self._kaltes_bild

    # ==================================================================
    #  Tor und Helligkeit
    # ==================================================================
    def freigegeben(self) -> bool:
        """Darf gezeichnet werden?

        ⚠ Primaer WLEDs Hauptschalter — er ist der echte Aus-Schalter der Anzeige. Nur wenn
        er GAR NICHT existiert oder unavailable/unknown meldet (Geraet stromlos, oder HA hat
        die Entitaet mangels zweitem Segment nicht angelegt), entscheidet der Stromschalter.
        Sonst gaebe es eine Henne-Ei-Falle: ohne zweites Segment kein Hauptschalter, ohne
        Hauptschalter kein Rendern — und gerade das Rendern legt das zweite Segment an.

        ★★ Und ohne Stromschalter? Bis 0.5.14 stand hier ein `return False` — und damit die
        Falle in Reinform. Am 03.08.2026 an der kleinen Matrix erlebt: sie verlor beim
        Aus- und Einschalten ihr zweites Segment, HA legte den Hauptschalter deshalb nicht
        mehr an, die Entitaet blieb `unavailable` mit `restored: true` — und die App
        zeichnete nie wieder, obwohl das Geraet die ganze Zeit im Netz war und auf seine
        API antwortete. Ein HA-Neustart half nicht, weil die Ursache am Geraet sass.

        Deshalb: **ohne Rueckfall im Zweifel ZEICHNEN.** Der Versuch kostet nichts —
        entweder er gelingt (dann entsteht das zweite Segment, HA legt den Hauptschalter
        an, und alles ordnet sich von selbst), oder er scheitert und meldet ehrlich einen
        Sendefehler. Beides ist besser als ein Stillstand, aus dem es keinen Weg heraus
        gibt.
        """
        p = self.cfg
        if not p.gate_entity:
            return True
        zustand = self.ha.state(p.gate_entity)
        if zustand in ("on", "off"):
            return zustand == "on"
        if p.gate_fallback:
            return self.ha.state(p.gate_fallback) == "on"
        # Tor unbrauchbar UND kein Rueckfall: zeichnen (siehe oben) statt festzufahren.
        return True

    async def schalte(self, an: bool) -> tuple[bool, str]:
        """Die Anzeige ein- oder ausschalten. Rueckgabe: (geklappt, was getan wurde).

        ★ Ist ein `gate.script` eingetragen, wird DAS gerufen und sonst nichts. Grund aus
        der Praxis: an der Wohnzimmer-Matrix haengt der ESP32 am selben Strom wie die
        Panels. Beim Einschalten muss er erst booten und ins WLAN, BEVOR HA seinen
        Konfigurationseintrag aktivieren darf — sonst scheitert die Einrichtung an einem
        nicht erreichbaren Geraet, und HA wartet danach mit wachsenden Abstaenden.
        Ausgeschaltet wird in umgekehrter Reihenfolge: erst die Anbindung weg, dann der
        Strom, sonst protokolliert HA Verbindungsfehler.

        Diese Reihenfolge samt gemessener Wartezeiten gehoert in ein HA-Skript, nicht
        hierher: das Aktivieren eines KONFIGURATIONSEINTRAGS ist nichts, was eine
        Render-App tun sollte, und die Eintrags-Kennung kennt sie auch nicht.

        Ohne Skript wird das Tor direkt geschaltet — fuer einfache Aufbauten, bei denen
        der Strom durchgehend anliegt.
        """
        p = self.cfg
        if p.gate_script:
            # ⚠ Ein Skript kennt kein "aus": `script.turn_on` startet es, und das Skript
            # selbst entscheidet anhand des aktuellen Zustands, in welche Richtung es
            # schaltet (Umschalter). Deshalb wird hier NICHT nach `an` unterschieden —
            # wer das aendert, muss das Skript mit aendern.
            ok = await self.ha.rufe_dienst(p.gate_script, "turn_on")
            return ok, f"Skript {p.gate_script} gestartet"

        ziel = p.gate_entity or p.gate_fallback
        if not ziel:
            return False, "kein Tor und kein Rueckfall konfiguriert"
        # Existiert das Tor gerade nicht (Geraet stromlos), ueber den Rueckfall gehen —
        # sonst kaeme man nie wieder an: das Tor entsteht erst MIT dem Geraet.
        if p.gate_entity and self.ha.state(p.gate_entity) in (None, "unavailable", "unknown") \
                and p.gate_fallback:
            ziel = p.gate_fallback
        ok = await self.ha.rufe_dienst(ziel, "turn_on" if an else "turn_off")
        return ok, f"{ziel} {'an' if an else 'aus'}"

    def helligkeit(self) -> int:
        """Die geltende Helligkeit.

        ⚠ Bei konfigurierter Entitaet kommt der Wert aus HAs Zustandsspiegel — und der
        zieht erst nach, wenn das `state_changed`-Ereignis eingetroffen ist. Direkt nach
        einem eigenen `set_value` meldete diese Funktion deshalb noch den ALTEN Wert:
        die Antwort auf `POST …/helligkeit` sagte 23, obwohl gerade 30 gesetzt worden
        war, und der naechste `/api/panels`-Abruf widersprach dem Regler.

        Deshalb gilt der selbst gesetzte Wert vorrangig, bis der Spiegel ihn bestaetigt.
        Die Verfallszeit ist die Notbremse: kommt die Bestaetigung nie (Entitaet lehnt
        ab, Ereignis verloren), darf die Anzeige nicht dauerhaft etwas behaupten, was
        nicht gilt — dann gewinnt wieder der Spiegel.
        """
        p = self.cfg
        if not p.brightness_entity:
            return self._eigene_helligkeit
        try:
            gelesen = max(1, min(255, int(float(self.ha.state(p.brightness_entity)))))
        except (TypeError, ValueError):
            gelesen = p.brightness_default

        gesetzt, gueltig_bis = self._gesetzte_helligkeit
        if gesetzt is not None:
            if gelesen == gesetzt or time.monotonic() > gueltig_bis:
                self._gesetzte_helligkeit = (None, 0.0)
            else:
                return gesetzt
        return gelesen

    # ==================================================================
    #  Schleife
    # ==================================================================
    async def run(self, session: aiohttp.ClientSession) -> None:
        await self.ha.bereit.wait()
        self.starte_beobachtung()
        _LOG.info("%s: Anzeige laeuft (%dx%d @ %s, alle %.1fs)%s",
                  self.cfg.id, self.cfg.width, self.cfg.height, self.cfg.host,
                  self.cfg.interval,
                  "  — PROBELAUF, es wird NICHTS gesendet" if self.cfg.dry_run else "")
        while True:
            try:
                await self._takt(session)
            except asyncio.CancelledError:
                raise
            except Exception:
                _LOG.exception("%s: Takt gescheitert", self.cfg.id)
            try:
                await asyncio.wait_for(self._sofort.wait(), timeout=self.cfg.interval)
            except asyncio.TimeoutError:
                pass
            self._sofort.clear()

    async def _takt(self, session: aiohttp.ClientSession) -> None:
        # Ein Frame aus veralteten Werten waere schlimmer als gar keiner.
        if not self.ha.verbunden:
            return

        frei = self.freigegeben()
        if frei and not self._war_frei:
            # ★★ Beim EINSCHALTEN ein Vollbild erzwingen. WLED stellt beim Einschalten
            # seinen eigenen letzten Zustand her — je nach Voreinstellung eine Farbe oder
            # ein Effekt. Die App weiss davon nichts und wuerde nur die Unterschiede zum
            # zuletzt von IHR gesendeten Bild schicken; auf der Matrix bliebe dann alles
            # stehen, was sie nicht selbst gezeichnet hat. Am Geraet erlebt: nach dem
            # Einschalten war die Flaeche komplett rot und blieb es, bis das naechste
            # turnusmaessige Vollbild fiel (bei `full_frame_every: 60` und 5 s Takt also
            # bis zu fuenf Minuten).
            #
            # `_letztes = None` heisst fuer den Transport: nichts Bekanntes auf dem
            # Geraet, also die ganze Flaeche neu beschreiben.
            self.transport._letztes = None
            self._frei_seit = time.time()
            _LOG.info("%s: eingeschaltet — Vollbild erzwungen", self.cfg.id)
        self._war_frei = frei

        if not frei:
            # ★ Die Anzeige ist BEWUSST aus — dann ist „nicht erreichbar" keine Neuigkeit,
            # sondern die Folge. Ohne diese Zeile bliebe die rote Meldung fuer immer
            # stehen: geloescht wird `letzter_fehler` nur von einem erfolgreich
            # gesendeten Bild (siehe wled.py), und gesendet wird hier ja gerade nicht.
            # Beim Ausschalten geht typischerweise noch ein Block in die Zeitueberschreitung
            # — genau der eine Sendefehler, der danach als Dauerwarnung haengenblieb.
            # Der kumulative Zaehler `fehler` bleibt unangetastet: dass es geknirscht hat,
            # soll sichtbar bleiben.
            self.transport.stat.letzter_fehler = ""
            self._tor_nicht_on_seit = 0.0
            self._naechster_versuch = 0.0
            self._rueckzug = 0.0
            self.sendepause = ""
            return
        async with self._lock:
            # ★ Die Sperre umschliesst Bauen UND Senden. Der Frame wird in Bloecken
            # geschickt; jedes await dazwischen waere sonst eine Stelle, an der ein
            # zweiter Render (Umschalten, Benachrichtigung) dazwischenfunkt und auf der
            # Matrix ein Mischbild entsteht. Am Vorgaenger als Flackern beobachtet.
            ergebnis = self.renderer.frame(self._vorwahl, self._aktive_notizen())
            self.letztes_ergebnis = ergebnis
            self.letzter_lauf = time.time()
            if self.cfg.dry_run:
                # Probelauf: das Bild steht in der Vorschau, das Geraet sieht nichts.
                # Gemeldet wird trotzdem — gerade im Probelauf will man sehen, welcher
                # Screen greift und ob der Bildaufbau fehlerfrei durchlaeuft.
                self.transport.stat.frames += 1
            else:
                darf, probe, grund = self._sendefenster()
                self.sendepause = grund
                # ★ Gerechnet und gezeichnet wird trotzdem — nur geschickt wird nicht.
                # Sonst friere die Vorschau im Betriebs-Reiter ein, und man saehe nicht
                # mehr, was die App gerade darstellen WUERDE.
                if not darf:
                    return
                await self.transport.sende(session, ergebnis.bild, self.helligkeit(),
                                           ergebnis.scroll, probe=probe)
                self._rueckzug_fortschreiben()
                if self._faehrt_hoch():
                    # ★★ Waehrend das Geraet hochfaehrt sind Zeitueberschreitungen die
                    # Regel, keine Stoerung — sie als roten Kasten zu zeigen erschreckt
                    # ohne Grund.
                    #
                    # Am 02.08.2026 gemessen: Klick 20:10:18, Strom an 20:10:19,
                    # WLED erreichbar erst 20:10:39. In diesen 20 Sekunden stand das Tor
                    # auf `unavailable`, der Rueckfall (Stromschalter) auf `on` — die App
                    # hielt sich also fuer zeichenberechtigt und schickte ins Leere.
                    #
                    # Der Zaehler `fehler` bleibt stehen: dass es geknirscht hat, soll
                    # sichtbar bleiben, nur eben nicht als Alarm.
                    self.transport.stat.letzter_fehler = ""

    def _sendefenster(self) -> tuple[bool, bool, str]:
        """Darf JETZT gesendet werden? Rueckgabe: (darf, ist_probe, Grund der Pause).

        ★★ `freigegeben()` beantwortet „darf gezeichnet werden?" — eine Zustandsfrage an
        Home Assistant. Bis 0.19.2 wurde die Antwort benutzt, als haette sie „kann
        gesendet werden?" beantwortet, und das ist etwas anderes: beim Einschalten liegt
        20 Sekunden lang Strom an, bevor WLED im Netz ist (Messung siehe `NOTAUSGANG_S`).

        Die Trennung hier:

        * Tor meldet `on`   → HA spricht mit dem Geraet, also senden. Normalfall.
        * Tor meldet es nicht (unavailable/unknown/fehlt) → bis zu `NOTAUSGANG_S` warten.
          Das deckt den Hochlauf ab, ohne einen einzigen Versuch ins Leere.
        * Danach trotzdem einmal versuchen, aber als **Probe** — genau dieser Versuch
          loest die Henne-Ei-Falle aus `freigegeben()`: ohne zweites Segment legt HA den
          Hauptschalter nicht an, und erst das Zeichnen legt das Segment an. Klappt er,
          ordnet sich alles von selbst; klappt er nicht, gilt das Geraet als weg.

        `_naechster_versuch` steht ueber allem: nach einem gescheiterten Versuch wird
        zurueckgezogen, egal auf welchem Weg er zustande kam.
        """
        jetzt = time.time()
        if jetzt < self._naechster_versuch:
            return False, False, f"Rueckzug, naechster Versuch in {self._naechster_versuch - jetzt:.0f} s"

        p = self.cfg
        # Ohne Tor gibt es nichts, worauf man warten koennte — dann wie bisher senden.
        tor = self.ha.state(p.gate_entity) if p.gate_entity else "on"
        if tor == "on":
            self._tor_nicht_on_seit = 0.0
            return True, False, ""

        if not self._tor_nicht_on_seit:
            self._tor_nicht_on_seit = jetzt
        wartet = jetzt - self._tor_nicht_on_seit
        frist = p.gate_wartezeit
        if wartet < frist:
            return False, True, f"wartet auf {p.gate_entity} (noch {frist - wartet:.0f} s)"
        return True, True, ""

    def _rueckzug_fortschreiben(self) -> None:
        """Nach dem Senden: bei Erfolg zurueck in den Takt, sonst weiter zurueckziehen.

        Verdoppelnd bis `RUECKZUG_MAX_S`, Start beim doppelten Takt — bei 5 s also
        10, 20, 40, 60, 60 … Ein Geraet, das ueber Nacht stromlos ist, wird damit
        stuendlich 60-mal angerufen statt 720-mal.
        """
        if self.transport.stat.erreichbar:
            self._rueckzug = 0.0
            self._naechster_versuch = 0.0
            return
        self._rueckzug = min(RUECKZUG_MAX_S,
                             max(self.cfg.interval * 2, self._rueckzug * 2))
        self._naechster_versuch = time.time() + self._rueckzug

    def _faehrt_hoch(self) -> bool:
        """Faehrt das Geraet gerade hoch — sind Sendefehler also zu erwarten?

        Eine einzige Bedingung: es ist noch nicht lange her, dass eingeschaltet wurde.

        ⚠ In 0.5.12 standen hier noch zwei zusaetzliche Bedingungen — das Tor musste
        `unavailable` melden und ein Rueckfall konfiguriert sein. Das war zu eng gefasst
        und ging am 03.08.2026 schief: nach dem Einschalten der grossen Matrix ueber ihr
        Skript kam nach 3 Sekunden

            nicht erreichbar (Cannot connect to host 192.168.1.50:80)

        als roter Kasten — weil HA den Hauptschalter zu dem Zeitpunkt schon wieder `on`
        meldete, obwohl WLED noch gar nicht im Netz war. Der Zustand des Tors sagt eben
        nichts darueber, ob das Geraet ANTWORTET.

        Die Zeitgrenze allein reicht und ist ehrlicher: ein Geraet, das gar nicht
        hochkommt, meldet nach einer Minute wieder Fehler. Ohne sie bliebe ein totes
        Geraet fuer immer stumm.
        """
        return (time.time() - self._frei_seit) < HOCHLAUF_S
