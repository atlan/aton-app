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


@dataclass
class Notiz:
    text: str
    level: str = "info"
    bis: float | None = None
    prio: int = 1
    lfd: int = 0


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
        # War die Anzeige beim vorigen Takt freigegeben? Der Wechsel aus/ein erzwingt ein
        # Vollbild. Startwert False: beim allerersten Takt weiss die App ohnehin nicht,
        # was auf dem Geraet steht — also gleich die ganze Flaeche beschreiben.
        self._war_frei = False
        # Wann wurde zuletzt eingeschaltet? Bezugspunkt fuer die Hochlauf-Nachsicht.
        self._frei_seit = 0.0

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
        if level not in self.cfg.notify.levels:
            level = "info"

        try:
            dauer = float(d.get("duration", 30))
        except (TypeError, ValueError):
            dauer = 30.0
        try:
            prio = int(d.get("priority", 2 if level == "warning" else 1))
        except (TypeError, ValueError):
            prio = 2 if level == "warning" else 1

        self._notizen[nid] = Notiz(
            text=str(d.get("text", "")),
            level=level,
            bis=(time.time() + dauer) if dauer > 0 else None,
            prio=prio,
            lfd=self._lfd,
        )
        self._sofort.set()
        return nid

    def notiz_loeschen(self, nid: str | None = None) -> None:
        """Eine Meldung loeschen — ohne Kennung alle."""
        if not nid:
            self._notizen.clear()
        else:
            self._notizen.pop(str(nid), None)
        self._sofort.set()

    def _aktive_notiz(self) -> dict | None:
        jetzt = time.time()
        for nid, n in list(self._notizen.items()):
            if n.bis is not None and n.bis <= jetzt:
                del self._notizen[nid]
        if not self._notizen:
            return None
        beste = max(self._notizen.values(), key=lambda n: (n.prio, n.lfd))
        return {"text": beste.text, "level": beste.level}

    @property
    def vorwahl(self) -> dict[str, str | None]:
        """Handauswahl je Screen-Gruppe; None = Automatik."""
        return dict(self._vorwahl)

    def aktive_notiz(self) -> dict | None:
        return self._aktive_notiz()

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
            return
        async with self._lock:
            # ★ Die Sperre umschliesst Bauen UND Senden. Der Frame wird in Bloecken
            # geschickt; jedes await dazwischen waere sonst eine Stelle, an der ein
            # zweiter Render (Umschalten, Benachrichtigung) dazwischenfunkt und auf der
            # Matrix ein Mischbild entsteht. Am Vorgaenger als Flackern beobachtet.
            ergebnis = self.renderer.frame(self._vorwahl, self._aktive_notiz())
            self.letztes_ergebnis = ergebnis
            self.letzter_lauf = time.time()
            if self.cfg.dry_run:
                # Probelauf: das Bild steht in der Vorschau, das Geraet sieht nichts.
                # Gemeldet wird trotzdem — gerade im Probelauf will man sehen, welcher
                # Screen greift und ob der Bildaufbau fehlerfrei durchlaeuft.
                self.transport.stat.frames += 1
            else:
                await self.transport.sende(session, ergebnis.bild, self.helligkeit(),
                                           ergebnis.scroll_text)
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
