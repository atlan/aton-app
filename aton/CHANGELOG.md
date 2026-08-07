# Änderungen

## 0.11.7 — der Zoom folgt jetzt der Spaltenbreite

0.11.6 hat die Rahmen an das verkleinerte Bild angepasst — richtig, aber die
Pixelgrafik blieb weichgerechnet. Jetzt wird der Zoom **vor** dem Abruf aus der
Spaltenbreite bestimmt, sodass der Server das Bild gleich passend rendert.

Gemessen an derselben Seite:

| Fenster | Spalte | Zoom | Bild | Faktor |
|---|---|---|---|---|
| 1720 | 1080 | 8 | 1024 px | **1,0** |
| 1200 | 560 | 4 | 512 px | **1,0** |

Ein ganzzahliger Zoom heißt scharfe LED-Punkte; vorher lag der Faktor bei krummen
0,931 und verschmierte sie.

⚠⚠ **Gerechnet wird aus der Spaltenbreite, niemals aus dem zurückgemeldeten Zoom.**
Wer `K.zoomWunsch = p.zoom` schreibt, baut eine Rückkopplung: bei gesetztem
`led_pitch` weicht der benutzte vom angeforderten Zoom ab, und das Bild schrumpft
dann bei jedem Durchlauf weiter (6 → 5 → 4 …). Die Spalte ist `minmax(320px, 1fr)`
und hängt nicht am Bild — deshalb dreht sich nichts im Kreis.

`max-width: 100%` und der Faktor aus 0.11.6 bleiben als Netz: bei `led_pitch` über
P3 kann der Server einen größeren Zoom benutzen als angefordert.

## 0.11.5/0.11.6 — die Kachelrahmen ragten aus der Vorschau heraus

Vom Nutzer an einem Screenshot bemerkt: „die feldrahmen ragen über den preview
hinaus". Kein Anzeigefehler des Bildes, sondern ein echter Fehler der Oberfläche.

★ **Zwei Maßstäbe, die nicht zusammenpassten.** `.k-buehne img` hat
`max-width: 100%` — sobald die mittlere Spalte schmaler ist als Matrixbreite × Zoom
(bei 128 px und Zoom 6 also 768 px), rechnet der Browser das **Bild** herunter. Die
**Kachelrahmen** wurden aber weiter in ungerechneten Zoom-Pixeln gesetzt. Bei 1400 px
Fensterbreite gemessen: Bühne 715 px breit, Inhalt 770 px, sechs Elemente über dem
Rand — sichtbar im Formular daneben.

Behoben mit einem dritten Faktor `K.skala` (tatsächliche ÷ natürliche Bildbreite), der
sowohl die Rahmen setzt als auch die Ziehwege umrechnet — sonst wäre die Kachel unter
dem Mauszeiger weggewandert. Danach gemessen: 0 Elemente über dem Rand.

⚠ Zwei Fallen dabei, beide beim Bauen getroffen:

- `clientWidth` ist **0**, solange der Reiter versteckt ist (`section[hidden]`). Ohne
  Rückfall auf Faktor 1 fielen alle Rahmen auf Größe null zusammen.
- Der Faktor ändert sich beim Ziehen am Fensterrand und beim Wechsel auf den Reiter.
  Beides stößt das Setzen jetzt erneut an.

## 0.11.4 — die Hände an den Strahlen fehlten

Der erste Ausschnitt fürs Icon nahm die Scheibe plus den **oberen** Teil der Strahlen
— und schnitt damit genau die **Hände** ab, also das Kennzeichen des Zeichens. Vom
Nutzer bemängelt, zu Recht.

★ **Der Schnitt geht seitlich, niemals waagerecht.** Weniger Strahlen (die mittleren
45 % der Breite), dafür ganze: so wird das Zeichen fast quadratisch und passt ohne
Verlust ins Icon. Die Verdickung liegt hier bei ×4 statt ×2 wie beim Logo, weil im
Quadrat weniger Höhe zur Verfügung steht — bei 40 × 40 trägt das Zeichen rund 31 px.

Vier Varianten wurden wieder in echter Anzeigegröße verglichen. Begründung steht im
Generator, damit der waagerechte Schnitt nicht zurückkommt.

## 0.11.3 — ein Motiv überall: das Punktraster ist raus

Das Aton-Zeichen gilt jetzt für **alle** Bilder, nicht nur fürs Logo:

| Datei | Größe | wo sie auftaucht |
|---|---|---|
| `aton/icon.png` | 128×128 | Liste der installierten Apps (mit 40×40 gezeigt) |
| `aton/logo.png` | 524×256 | Detailseite der App (mit 82×40 gezeigt) |
| `aton/www/icon.png` | 256×256 | Favicon und Kopf der eigenen Oberfläche |
| `brand/icon.png` | 256×256 | PR nach `home-assistant/brands` (Integrations-Kachel) |
| `brand/icon@2x.png` | 512×512 | dito, hDPI |

★ **Das Icon zeigt einen AUSSCHNITT, nicht das ganze Zeichen.** Aton ist 2,3:1 breit;
in ein Quadrat gesetzt bliebe es keine 14 px hoch, wenn HA das Icon mit 40×40 zeigt —
die Strahlen wären dann 0,14 px breit und schlicht nicht da. Vier Varianten wurden in
echter Größe verglichen: das ganze Zeichen wird zum Fleck, der Ausschnitt (Scheibe plus
oberer Teil der Strahlen) trägt und nutzt die Quadratfläche.

Die brands-Dateien sind gegen die dortigen Regeln geprüft: 256 bzw. 512 exakt,
quadratisch, PNG mit Transparenz, nicht byteidentisch, randlos.

## 0.11.2 — neues Logo: das Aton-Zeichen, ohne Schrift

Auf Wunsch des Nutzers zeigt das Logo jetzt **Aton selbst** — die Sonnenscheibe mit
den Strahlen, die in Haenden enden — und keine Wortmarke mehr.

Vorlage ist [Aten.svg](https://commons.wikimedia.org/wiki/File:Aten.svg) von AtonX.
⚠ Die Datei steht unter mehreren Lizenzen zur Wahl; genutzt wird sie unter
**CC BY 2.5**, der einzigen darunter OHNE Share-alike — fuer ein veroeffentlichtes
Repo die unbedenklichste. Namensnennung im README, Herkunft und Aenderungen in
der Herkunftsvermerk beim Bildgenerator.

★ **Die Strahlen mussten verdickt werden, sonst waren sie weg.** Im Original sind sie
bei 400 px Hoehe ~4 px breit — bei den 40 px, mit denen HA das Logo zeigt, bleiben
davon 0,5 px, und sie erscheinen als olivgraue Schlieren statt als goldene Strahlen.
Fuenf Abstufungen in echter Anzeigegroesse verglichen: ab ×3 verschmelzen sie zum
Faecher, ×2 haelt sie einzeln und golden. Genau dieser Wert steht jetzt im Generator,
mit der Begruendung daneben.

## 0.11.1 — Store-Eintrag: englische Beschreibung, lesbares Logo

Beim Blick auf die Store-Karte aufgefallen, dass zwei Dinge noch deutsch waren:

- **`description:`** in `config.yaml` — das ist der Text, den der App-Store zeigt.
  Jetzt Englisch, und ohne Schlusspunkt: Home Assistant haengt selbst einen Satz an
  („Weitere Informationen findest du auf der Seite …"), vorher standen dort zwei Punkte.
- **`logo.png`** trug eine Unterzeile („LED-Matrix als Anzeigetafel für Home Assistant").

★ **Beim Logo war die Sprache aber gar nicht das Problem.** Der Store zeigt das Banner
rund 180 px breit; ein 1000-px-Bild landet damit bei einem Fuenftel, und eine Zeile von
14 px Hoehe hat dort keine 3 px mehr — sie ist grundsaetzlich nicht lesbar, egal was
drinsteht. Dazu steht die Beschreibung im Store ohnehin direkt darunter.

**Unterzeile deshalb ersatzlos raus**, die Wortmarke nutzt jetzt die ganze Hoehe. In
Store-Groesse nachgestellt und geprueft: „Aton" ist klar zu lesen. Dasselbe fuer Renpet.

## 0.11.0 — Dokumentation auf Englisch, mit Bildern

Vorbereitung der Veroeffentlichung. `README.md` und `aton/DOCS.md` sind neu und
auf Englisch; der CHANGELOG bleibt Deutsch (Arbeitsjournal), neue Eintraege
schreibe ich ab jetzt aber ebenfalls auf Englisch, sobald das Repo oeffentlich ist.

Neu unter `docs/`:

- `getting-started.md` — vom Installieren bis zum ersten Bild, mit dem Screenshot
  des Betriebs-Reiters und einer Tabelle, was dort abzulesen ist.
- `yaml-reference.md` — jeder Schluessel mit Beispiel: Tor, Helligkeit,
  `led_pitch`, Widgets, Screen-Gruppen, **Seiten mit ungleichen Standzeiten**,
  Meldungen, Schriften, eigene Symbole, Vorlagen, Entitaeten in HA.
- `configurator.md` — Baum, Vorschau, Formular; Anlegen, Verschieben, Pruefen,
  Speichern, Sicherungen; die beiden bekannten Grenzen (`on`/`off` in `map:`,
  Kommentare an Listeneintraegen).

`aton/DOCS.md` ist bewusst die KURZE Fassung ohne Bilder — HA zeigt in der
App-Oberflaeche nur diese Datei an und rendert Bilder darin nicht zuverlaessig.
Sie verweist auf die ausfuehrlichen Seiten.

Alle Warnungen aus der bisherigen Doku sind mitgenommen, keine gestrichen — dazu
zwei, die beim Schreiben des Beispiels aufgefallen sind: ein `gate.fallback` auf
eine nicht existierende Entitaet zaehlt als AUS (dann zeichnet die App gar
nichts), und `states(...) | round(0)` wirft bei fehlender Entitaet, weil
`states()` den Text `unknown` liefert.

## 0.10.5 — die Oberfläche ist jetzt wirklich zweisprachig

Bisher kannte nur der Konfigurator Sprachen. Der **Betriebs-Reiter** enthielt kein
einziges `T(` — „Betrieb", „Ausschalten", „Helligkeit", „Bilder" standen fest im
Quelltext. Bei englischer Oberflaeche ergab das ein Kauderwelsch aus beidem, was
fuer eine Veroeffentlichung nicht taugt.

- `index.html` durchgaengig auf `T()` und `data-i18n` umgestellt; `statischeTexte()`
  fuellt alles mit `data-i18n` generisch, eine neue Beschriftung braucht also nur
  noch das Attribut. Der deutsche Text bleibt im Markup als Rueckfall stehen.
- 14 fehlende Schluessel in beiden Sprachen ergaenzt; im Konfigurator waren „Vorlage"
  und „fest" uebrig geblieben.
- Zahlformat folgt der Sprache (`de-DE` / `en-GB`) statt fest deutsch zu sein.
- ⚠ **Nur die Beschriftung** von „Automatik" ist uebersetzt — der WERT bleibt
  `Automatik`, er geht so an den Server und steht als Stellung in der Beschreibung.

### ★★ Drei Fehler, die dabei ans Licht kamen

1. **`window.K` war immer `undefined`.** `K` ist ein `const` auf oberster Ebene, und
   das legt keine Eigenschaft auf `window` an. Drei Pruefungen hingen daran und
   trafen deshalb nie zu: die Nachfrage nach ungespeicherten Aenderungen erschien
   nicht, das Zahlformat blieb immer deutsch. Jetzt `typeof K`.
2. Beim Sprachwechsel muessen die Karten neu aufgebaut werden. Sie merken sich das
   mit **vier** Merkern (`schalter`, `regler`, `vollbild`, `aufgebaut`); zwei davon
   hatte ich uebersehen — Schalter und Regler verschwanden dann ganz. Wird jetzt
   generisch abgeraeumt.
3. `betriebNeuZeichnen` muss eine Funktions-DEKLARATION auf oberster Ebene sein,
   sonst findet `konfigurator.js` sie nicht.

## 0.10.2 — die Helligkeits-Antwort meldete den alten Wert

`POST /api/panel/<id>/helligkeit` las den Wert nach dem Setzen zurueck, und
`helligkeit()` liest bei konfigurierter `brightness.entity` aus HAs Zustandsspiegel.
Der zieht erst mit dem `state_changed`-Ereignis nach — die Antwort behauptete
deshalb den ALTEN Wert (gemessen: gesetzt 30, gemeldet 23), und der naechste
`/api/panels`-Abruf widersprach dem Regler.

- `setze_helligkeit()` liefert jetzt den **tatsaechlich gesetzten** Wert (nach
  Begrenzung auf 1..255) statt `True`, und `None`, wenn es nicht ging. Der Endpunkt
  meldet diesen Wert, statt ihn zurueckzuholen.
- `helligkeit()` gibt dem selbst gesetzten Wert **Vorrang, bis der Spiegel ihn
  bestaetigt** — hoechstens 10 s. Danach gewinnt wieder der Spiegel, damit eine nie
  eintreffende Bestaetigung (Entitaet lehnt ab, Ereignis verloren) die Anzeige nicht
  dauerhaft etwas behaupten laesst, was nicht gilt.

Damit ist es dieselbe Regel wie in der Oberflaeche seit 0.10.1, nur eine Ebene
tiefer — und sie gilt jetzt fuer **jeden** Aufrufer der API, nicht nur fuer den
eigenen Konfigurator.

## 0.10.1 — die Betriebsansicht nimmt die Steuerung nicht mehr aus der Hand

Der Nutzer musste die Screen-Auswahl „Felder 1-12" mehrfach umschalten, bis sie
griff; beim Helligkeitsregler dasselbe Gefuehl.

Ursache: alle drei Sekunden schrieb `betriebHolen()` die Server-Werte in **jedes**
Bedienelement zurueck — auch wenn sich gar nichts geaendert hatte. Wer im falschen
Moment tippte, arbeitete gegen diesen Takt.

- **Es wird nur noch geschrieben, wenn der Server einen ANDEREN Wert meldet als beim
  letzten Abruf.** Im Ruhezustand werden Regler und Auswahl gar nicht mehr angefasst;
  Bild und Lesewerte laufen weiter wie bisher. Eine Aenderung von aussen (Home
  Assistant, zweiter Browser) kommt trotzdem an — dann ist der Wert ja neu.
- **Der eigene Befehl wird verteidigt**, bis der Server genau ihn bestaetigt
  (`wunschSetzen`/`wunschHaelt`). Vorher konnte eine spaet eintreffende Antwort den
  alten Stand zurueckschreiben; es sah aus, als haette der Klick nicht gegriffen —
  woraufhin man erneut klickte und gegen den eigenen vorherigen Befehl arbeitete.
  15 s Frist als Notbremse, damit ein verlorener Befehl die Anzeige nicht dauerhaft
  auf einem Wunsch stehen laesst, den es nicht gibt.
- Die Screen-Auswahl ruft jetzt `bedient()` bei `pointerdown` und `focus` — der
  Regler daneben tat das laengst, die Auswahl an keiner Stelle.

## 0.10.0 — Seiten dürfen unterschiedlich lange stehen

Bisher galt `wechsel_zyklen` fuer den ganzen Screen: alle Seiten standen gleich
lang. Jede Seite hat jetzt ein eigenes Feld **„Diese Seite steht"** (`zyklen`).
Damit geht „Uebersicht 2 Zyklen, Details nur 1".

- **0 = so lange wie im Screen eingestellt.** Wer nichts eintraegt, merkt nichts:
  bei gleichen Standzeiten faellt die Rechnung auf die alte Formel zurueck, ueber
  20 000 Zeitpunkte gegengeprueft.
- `wechsel_zyklen` bleibt der **Hauptschalter**: steht er auf 0, wechselt gar
  nichts — auch wenn einzelne Seiten eine Zahl tragen. Sonst waere die
  dokumentierte Bedeutung „0 = nur die erste" mal wahr und mal nicht.
- Gerechnet wird weiter mit der **Uhr**, nicht mit einem Bildzaehler: zwei
  Anzeigen duerfen nicht auseinanderlaufen, und die Vorschau im Konfigurator
  darf den Wechsel nicht mit hochzaehlen.

## 0.9.0 — Kennung durchgezogen: slug, Domain, Dateinamen

0.8.0 hatte nur die NAMEN umbenannt; slug und Integrations-Domain blieben
`matrix_panel`. Auf Wunsch des Nutzers jetzt vollstaendig:

- `slug: matrix_panel` → **`aton`** (App heisst `local_aton`)
- `DOMAIN = "matrix_panel"` → **`aton`**, Verzeichnis `custom_components/aton`
- Selbstanmeldung beim Supervisor: `service: aton`
- `config_file: matrix_panel.yaml` → **`aton.yaml`**
- `matrix_icons` → **`aton_icons`**, `matrix_fonts` → **`aton_fonts`**
- Sicherungsordner → **`aton_sicherungen`** (alter Ordner wird einmalig umgezogen)
- Dienste `matrix_panel.notify` → **`aton.notify`**, `.notify_clear` entsprechend

⚠ **Das ist ein Bruch, kein Umbenennen.** Die Integration muss neu eingerichtet
werden; Geraete und Entitaeten entstehen dabei NEU. Die Entitaets-IDs werden aus
dem AKTUELLEN Anzeigenamen gebildet — nicht aus dem, der beim ersten Anlegen galt.
In der Anlage des Autors hiess `select.matrix_wohnzimmer_felder_1_8` danach
`select.matrix_wohnzimmer_side_felder_1_12`: die alte ID stammte noch aus einer
Zeit vor dem Zusatz „Side" UND vor der Erweiterung der Gruppe von 8 auf 12 Felder.

**Wer aktualisiert, sollte vorher wissen, welche Entitaets-IDs in Automationen,
Skripten, Dashboards und Geraete-Firmware stehen** — sie aendern sich womoeglich
alle.

## 0.8.0 — heisst jetzt Aton

Umbenannt nach dem aegyptischen Sonnengott: die Sonnenscheibe, deren Strahlen in Haenden
enden — eine Flaeche, die Licht aussendet. Passt zu Osiris, Horus, Anubis und den
uebrigen Geraeten im Haus. Deutsche Schreibung (Aton, wie in Echnaton), nicht Aten.

Geaendert wurden **nur Namen**: App-Name, Seitenleisten-Eintrag, Titel der Oberflaeche,
Name der Begleit-Integration, Repo-URL und die Verzeichnisse (`matrix_panel/` → `aton/`).

⚠ **Bewusst NICHT geaendert**, weil daran Bestand haengt:

- `slug: matrix_panel` — der Add-on-Slug bleibt `local_matrix_panel`.
- `DOMAIN = "matrix_panel"` der Begleit-Integration.
- Damit bleiben **Geraet und alle Entitaeten** samt ihrer `unique_id` erhalten. Ein
  Wechsel wuerde einen kompletten zweiten Satz Entitaeten anlegen und den alten als
  `unavailable` liegenlassen — und die Osiris-Firmware hat
  `select.matrix_wohnzimmer_felder_1_8` fest verdrahtet.
- `config_file: matrix_panel.yaml` und die Ordner `matrix_icons` / `matrix_fonts` in
  `/config` — das sind Daten des Nutzers, keine Namen der App.

Slug, Domain und Dateinamen gehoeren in einen eigenen Umbau mit Migrationspfad,
sinnvollerweise gebuendelt mit der Veroeffentlichung.

## 0.7.0 — 06.08.2026

**★★ Die Kennung der Oberflächendateien steckt jetzt im DATEINAMEN, nicht im
Query-Teil** — `static/konfigurator.1785971601.js` statt `static/konfigurator.js?v=…`.

Der Grund ist am Gerät belegt und war teuer: `…js?v=123` sieht für einen Service Worker
aus wie `…js`. Er darf den Query beim Nachschlagen ignorieren und mit einer alten Kopie
antworten — egal welche Kennung dranhängt. Genau das ist passiert: der Server lieferte
nachweislich die neue Datei aus (durch Ingress gemessen), der Browser führte stundenlang
die alte aus, und **jede** Maßnahme auf Serverseite blieb wirkungslos.

Erkennbar war es am Ende an einer einzigen Stelle: die Daten im Browser waren neu
(`seiten` vorhanden), die Anzeige zeigte `0` — und `0` ist genau das, was der ALTE Code
auf NEUEN Daten liefert (`(sc.widgets || []).length`, wo es kein `widgets` mehr gibt).

Ein anderer **Pfad** ist ein anderer Eintrag im Zwischenspeicher. Daran kommt keiner
vorbei. Auf der Platte liegt weiterhin `konfigurator.js`; ein Handler führt den Namen
mit Kennung darauf zurück.

## 0.6.5 — 06.08.2026

**Die Veraltet-Warnung lief ausgerechnet im Konfigurator nie.** Sie hing in
`betriebHolen()`, und das bricht sofort ab, sobald der Betriebs-Reiter nicht sichtbar ist.
Wer im Konfigurator arbeitet — also dort, wo eine alte Fassung am meisten anrichtet —
bekam sie nie zu sehen; ein „der gelbe Kasten ist weg" bedeutete dort nicht „alles
aktuell", sondern „hier wird gar nicht geprüft".

Jetzt eigener Takt (alle 15 s, auf **jedem** Reiter) gegen den neuen, winzigen Endpunkt
`/api/stand`.

## 0.6.4 — 06.08.2026

**Der Veraltet-Hinweis war IMMER sichtbar** — mit leerem Text und einem Knopf, der
folgerichtig nichts bewirkte, weil es nichts zu beheben gab. Ursache: `#veraltet` hat ein
eigenes `display: flex`, und das überstimmt das `hidden`-Attribut (nur ein `display:none`
aus dem Browser-Standard, das gegen jede eigene Regel verliert). Behoben mit
`#veraltet[hidden] { display: none; }`.

⚠ Damit war der Hinweis in 0.6.1–0.6.3 wertlos: er zeigte nicht an, dass etwas veraltet
ist, sondern stand einfach immer da.

## 0.6.3 — 06.08.2026

**„Neu laden" lud neu — und zeigte trotzdem die alte Seite.** Diese Oberfläche läuft
unter HAs Ingress in einem eingebetteten Rahmen, und HAs Frontend hat einen Service
Worker. Der sitzt **vor** dem Netz und darf dieselbe Adresse aus seinem Zwischenspeicher
beantworten — das `no-store`, das die App mitschickt, erreicht ihn gar nicht.

Der Knopf lädt jetzt mit einer **anderen Adresse** (`?neu=<Zeitstempel>`, per
`location.replace`). Zwischenspeicher sind nach der vollständigen Adresse geschlüsselt;
ein neuer Parameter ist ein Fehlschlag darin und erzwingt den Gang ins Netz.

## 0.6.2 — 06.08.2026

**Der „Neu laden"-Knopf im Veraltet-Hinweis tat nichts.** Zwei Ursachen, beide behoben:

- Er hing als `onclick`-Attribut in der Seite — als einziger in der ganzen Datei, alles
  andere hängt seine Handler in JavaScript ein. Unter der Auslieferung durch HAs Ingress
  ist ein Inline-Attribut der einzige Weg, der still gar nichts tut.
- Der Konfigurator hängt einen `beforeunload`-Wächter ein, solange es ungespeicherte
  Änderungen gibt. In einem eingebetteten Rahmen bricht der Browser die Navigation dann
  **ohne Rückfrage** ab — der Knopf sah aus wie kaputt. Jetzt wird ausdrücklich gefragt
  und der Merker vorher zurückgenommen.

## 0.6.1 — 06.08.2026

**Die Oberfläche sagt jetzt, wenn im Browser eine alte Fassung läuft.** Zweimal an einem
Abend war genau das die Ursache einer langen Suche: der Server lieferte längst den neuen
Stand aus, im Tab lief der alte — und das sieht man einer Seite nicht an. Jede Beobachtung
steht dann unter Vorbehalt.

`/api/panels` (wird ohnehin alle drei Sekunden geholt) liefert den Stand mit, den der
Server *gerade* ausliefert. Weicht er von dem ab, mit dem die Seite geladen wurde, erscheint
oben ein Hinweis samt „Neu laden"-Knopf.

⚠ Die `?v=`-Kennung an den Skripten ist korrekt (Änderungszeit je Datei) — sie hilft aber
nur beim NÄCHSTEN Laden. Ein Tab, der seit Stunden offen ist, merkt von einer neuen Fassung
nichts. Genau diese Lücke schließt der Hinweis.

## 0.6.0 — 06.08.2026

**★★ Ein Screen kann jetzt mehrere `seiten:` haben — und die wechseln sich ab.** Damit
zeigen dieselben Kacheln abwechselnd Temperatur und Luftfeuchte, **ohne** dass daraus
zwei Stellungen in der Auswahl werden.

Das war der Fehler an 0.5.16/0.5.17: der Wechsel saß zwischen *Screens*. Zwei Screens
sind aber zwei Stellungen im `select` von Home Assistant — und eine Handauswahl hielt den
Wechsel an, weil sie genau eine Stellung festhält. Jetzt sitzt der Wechsel **im** Screen:
in der Auswahl steht weiterhin nur „Temperaturen", und gewechselt wird sowohl bei
Automatik als auch bei Handauswahl.

⚠ **Umzug:** `wechsel_zyklen` gehört an den SCREEN, nicht mehr an die Gruppe. Steht es
noch an der Gruppe, sagt die Prüfung das ausdrücklich statt „unbekannter Schlüssel".

```yaml
- name: Temperaturen           # eine Stellung in der Auswahl
  when: always
  wechsel_zyklen: 2            # Seiten alle 2 Bildtakte
  seiten:
    - name: Temperatur
      widgets: [ … °C … ]
    - name: Feuchte
      widgets: [ … % … ]
```

Ein Screen mit `widgets:` statt `seiten:` bleibt genau wie bisher — er hat dann intern
eine einzige Seite. Beides zugleich wird abgelehnt.

Im Konfigurator bekommen Screens mit Seiten eine Ebene mehr im Baum; die Klickflächen
im Vorschaubild folgen der **sichtbaren** Seite — sonst bearbeitete man ahnungslos eine
Kachel, die man gerade gar nicht sieht.

## 0.5.18 — 05.08.2026

**★★ Eine fehlerhafte Beschreibung beendet die App nicht mehr.** Vorher tat sie genau das
(`return 1`) — mit der bösen Folge, dass auch die **Oberfläche nie hochkam**: reparieren
ließ sich der Fehler dann nur noch über den Dateieditor oder die Konsole, also ausgerechnet
nicht dort, wo die Beschreibung sonst gepflegt wird. Dazu startete der Supervisor die App
in einer Schleife immer wieder neu.

Jetzt startet sie **ohne Anzeigen**, hält den Fehler fest und zeigt ihn im Betriebs-Reiter
als roten Kasten mit der genauen Stelle (`panels[0].screen_groups[0]: unbekannte
Schlüssel: …`). Korrigieren, *Neu laden* — fertig, ohne die App anzufassen.

**Umbenannte Felder werden übernommen statt abgelehnt.** Die Prüfung auf unbekannte
Schlüssel ist absichtlich streng (`valu` statt `value` soll laut scheitern), traf aber
auch jede Umbenennung. Bekannt-veraltete Namen stehen jetzt als solche im Schema
(`UMBENANNT`) und werden mit Hinweis im Protokoll übernommen — `wechsel_s: 10` wird bei
5 s Takt zu `wechsel_zyklen: 2`. Ein echter Tippfehler scheitert weiterhin.

## 0.5.17 — 05.08.2026

**Der Wechsel wird jetzt in Zyklen angegeben, nicht in Sekunden** (`wechsel_zyklen`
statt `wechsel_s`). Ein Zyklus ist ein Bildtakt — bei `interval: 5` sind zwei Zyklen
also zehn Sekunden. Grund: man denkt über diese Anzeige in Bildern, nicht in Sekunden,
und `full_frame_every` zählt aus demselben Grund schon so. Eine Angabe unterhalb eines
Zyklus, die gar nicht wirken kann, gibt es damit nicht mehr.

⚠ **Gerechnet wird weiterhin mit der Uhr** (Zyklen × Takt), nicht mit einem Bildzähler:
ein echter Zähler würde von der Vorschau im Konfigurator mit hochgezählt, und zwei
Anzeigen liefen mit der Zeit auseinander.

⚠ Wer 0.5.16 ausprobiert hat, ändert `wechsel_s: 10` in `wechsel_zyklen: 2`.

## 0.5.16 — 05.08.2026

**Screens einer Gruppe können sich abwechseln.** Neues Feld `wechsel_s` an der
Screen-Gruppe (Konfigurator: *Wechsel alle*, Sekunden, 0 = aus). Damit lässt sich
z.B. auf denselben acht Kacheln abwechselnd Temperatur und Luftfeuchte zeigen,
statt beides nebeneinander unterzubringen.

**Die Regel dahinter:** es wechseln nur **gleichrangige** Screens — alle mit derselben
Bedingung wie der Gewinner (`when: always` und ein fehlendes `when` sind dabei dasselbe).
Die Reihenfolge bleibt damit Vorrang: ein bedingter Screen verdrängt die Rückfälle wie
bisher, und „mehrere Screens für denselben Fall" heißt jetzt Abwechslung statt „der erste
gewinnt immer". Ohne `wechsel_s` ändert sich nichts.

Der Zeitpunkt kommt aus der Uhr, nicht aus einem Bildzähler: so hängt der Wechsel nicht
daran, wie oft gerendert wurde (Vorschau im Konfigurator, Nachzeichnen wegen einer
Meldung), und zwei Anzeigen mit gleichem Takt laufen synchron statt auseinander.
Die Handauswahl in Home Assistant schlägt den Wechsel weiterhin.

⚠ Kürzer als der Bildtakt (`interval`) wirkt nicht — bei 5 s Takt ist 5 s die feinste
sinnvolle Stufe.

## 0.5.15 — 03.08.2026

**★★ Eine Anzeige ohne `gate.fallback` konnte sich unrettbar festfahren.** Am Gerät
erlebt: die kleine Matrix verlor beim Aus- und Einschalten ihr zweites Segment. Home
Assistant legt den Hauptschalter aber **nur an, solange das Gerät mehr als ein Segment
hat** — die Entität blieb `unavailable` mit `restored: true`, die App zeichnete deshalb
nie wieder, und gerade das Zeichnen hätte das zweite Segment angelegt. Ein HA-Neustart
half nicht, weil die Ursache am Gerät saß.

Ohne Rückfall wird jetzt **im Zweifel gezeichnet**. Der Versuch kostet nichts: entweder er
gelingt — dann entsteht das zweite Segment, HA legt den Hauptschalter an und alles ordnet
sich von selbst — oder er scheitert und meldet ehrlich einen Sendefehler. Beides ist besser
als ein Stillstand ohne Ausweg.

⚠ Sofortabhilfe von Hand, falls es doch mal auftritt — das zweite Segment direkt anlegen:

```
curl -X POST -H "Content-Type: application/json" \
  -d '{"seg":[{"id":1,"on":false,"frz":false,"start":0,"stop":1,"startY":<h-1>,"stopY":<h>}]}' \
  http://<matrix>/json/state
```

**Die Hochlauf-Nachsicht war zu eng gefasst.** Sie verlangte zusätzlich, dass das Tor
`unavailable` meldet und ein Rückfall konfiguriert ist. Nach dem Einschalten der großen
Matrix über ihr Skript kam trotzdem ein roter Kasten, weil Home Assistant den Hauptschalter
da schon wieder `on` meldete, obwohl WLED noch nicht im Netz war. Der Zustand des Tors sagt
eben nichts darüber, ob das Gerät **antwortet**. Jetzt zählt nur noch das Zeitfenster von
60 s nach dem Einschalten.

## 0.5.14 — 02.08.2026

**Die Betriebsansicht fror ein und die Browser-Konsole lief voll.** Ursache war ein
Namenskonflikt, den ich in 0.5.11 selbst scharf gemacht habe:

```
konfigurator.js:52  Uncaught TypeError: pfad is not iterable
    at hole (konfigurator.js:52)
    at .../index:395        ← setInterval(() => hole(), 3000)
    at nachfassen           ← Nachfass-Schleife des Schalters
```

Es gibt **zwei** Funktionen namens `hole` im selben globalen Raum: die der Betriebsansicht
und `hole(pfad)` aus `konfigurator.js`, die später geladen wird und die erste überschreibt.
Lange folgenlos, weil `setInterval(hole, 3000)` die Referenz sofort festhielt — vor dem
Laden des Konfigurators. Mit der Pfeilfunktion aus 0.5.11 wird der Name dagegen bei **jedem**
Aufruf neu nachgeschlagen und trifft seither den Pfad-Helfer.

Die Funktion der Betriebsansicht heißt jetzt `betriebHolen`. Geprüft: zwischen dem
eingebetteten Skript, `konfigurator.js` und `symboleditor.js` gibt es **keine** gemeinsamen
globalen Namen mehr.

## 0.5.13 — 02.08.2026

**Ein einzelner fehlgeschlagener Abruf konnte die Oberfläche festfahren.** `hole()` fing
nichts ab — schlägt der Abruf fehl (etwa weil die App gerade neu startet), reißt die Kette
ab. Für den Zeitgeber wäre das folgenlos, für die Nachfass-Schleife des Schalters nicht:
die bricht dann ab und lässt den Knopf **für immer gesperrt** zurück. Ebenso beim
Schalt-Aufruf selbst — scheitert er, wird der Knopf jetzt in jedem Fall wieder freigegeben.

Kein Ersatz für ein Neuladen: läuft im Browser noch eine ältere Fassung der Seite, hilft
nur Strg-Umschalt-R. Der **Aufbaustempel neben dem Titel** sagt, welche Fassung geladen ist.

## 0.5.12 — 02.08.2026

**Nach dem Einschalten über ein Schaltskript kam ein roter Fehlerkasten.** Kein Fehlalarm
im engeren Sinne — die App hat wirklich ins Leere gesendet. Am Gerät gemessen:

```
20:10:18.86  script.lrtogglesidematrix → on    (Klick)
20:10:19.02  switch.liv_sidematrix     → on    (Strom an)
20:10:39.06  light.hub75_matrix_haupt  → on    (WLED im Netz, 20 s später)
```

In diesen 20 Sekunden steht das Tor auf `unavailable`. Dann greift der Rückfall auf den
Stromschalter — der sagt `on`, also hält sich die App für zeichenberechtigt und läuft in
Zeitüberschreitungen. Solche Fehler gehen jetzt für bis zu 60 Sekunden nach dem Einschalten
als „fährt hoch" durch, statt als Alarm zu erscheinen.

⚠ Bewusst mit Zeitgrenze: ein Gerät, das gar nicht hochkommt, meldet nach einer Minute
wieder ehrlich. Der kumulative Fehlerzähler bleibt in jedem Fall stehen — dass es
geknirscht hat, soll sichtbar bleiben.

## 0.5.11 — 02.08.2026

**Der Helligkeitsregler ruckelte beim Ziehen.** Den Wert vor dem Überschreiben zu schützen
reichte nicht: die Aktualisierung lief trotzdem alle drei Sekunden durch, holte für **jede**
Anzeige ein neues Vorschaubild und baute die Karte um — das stockt, und zwar genau unter
dem Finger, der gerade zieht. Während der Bedienung wird jetzt gar nicht mehr
aktualisiert; vier Sekunden nach dem Loslassen geht es weiter. Ausgelöst schon beim
Aufsetzen (`pointerdown`, deckt Maus, Finger und Stift ab), nicht erst bei der ersten
Wertänderung.

Aktionen des Benutzers überstimmen die Pause — sie kommen ja von ihm.

⚠ Dabei eine Falle vermieden: `setInterval(hole, 3000)` hätte `hole` das Zeitgeber-Argument
als „erzwingen" untergeschoben und die Pause damit wirkungslos gemacht. Jetzt über eine
Pfeilfunktion.

## 0.5.10 — 02.08.2026

**„Vollbild senden" stand zweimal da.** Den Knopf gab es längst — zwischen den
Screen-Wählern. Beim Verschieben in die Bedienzeile habe ich ihn verdoppelt statt versetzt.
Der alte ist weg. (Er hieß dort `b` und verdeckte damit die Bedienzeile `b` von weiter
oben — eine Verwechslung, die beim nächsten Griff darauf teuer geworden wäre.)

## 0.5.9 — 02.08.2026

**„Vollbild senden" steht jetzt im Betriebs-Reiter**, in derselben Zeile wie Schalter und
Helligkeit. Es gilt für jede Anzeige, unabhängig davon, ob ein Tor eingetragen ist —
bisher gab es den Weg nur über die Entität in Home Assistant. Nützlich, wenn auf der Matrix
etwas steht, das die App nicht gezeichnet hat.

**★ Die Helligkeit kam bis zu fünf Minuten zu spät am Gerät an.** Sie hängt am `rahmen`,
und der ging **nur beim Vollbild** raus — bei `full_frame_every: 60` und 5 s Takt also erst
beim nächsten turnusmäßigen Vollbild. Der Regler wirkte dadurch scheinbar gar nicht. Bei
einer Änderung wird sie jetzt ausdrücklich nachgeschickt; bei unverändertem Wert nicht,
sonst wäre es eine Anfrage mehr im 5-Sekunden-Takt für etwas, das sich fast nie bewegt.

⚠ Die App setzt die **Segment**-Helligkeit, nicht WLEDs globale. Deshalb bleibt in der
WLED-Oberfläche der eigene Wert stehen — beide multiplizieren sich. Das ist Absicht:
WLEDs globaler Regler gehört dem Benutzer.

**Der Helligkeitsregler sprang beim Ziehen zurück.** Alle drei Sekunden holt die Ansicht
die Werte neu und schreibt sie in die Bedienelemente. Die Prüfung auf `document.activeElement`
reicht bei Bedienung mit dem Finger oder nach einem Klick daneben nicht — jetzt zusätzlich
eine Schonfrist von vier Sekunden ab der letzten Berührung.

**Der Ein/Aus-Schalter reagiert schneller.** Er blieb stur drei Sekunden gesperrt, obwohl
ein direkt geschaltetes Tor den neuen Zustand in Sekundenbruchteilen meldet. Jetzt wird
kurz nachgefasst und freigegeben, sobald der Zustand wirklich umgesprungen ist — bei einem
Schaltskript weiterhin geduldig bis 45 s, weil dort Booten, Konfigurationseintrag und
Vollbild dazwischenliegen. Ob ein Skript im Spiel ist, sagt jetzt die Antwort des Servers,
statt dass die Oberfläche im Meldungstext herumrät.

## 0.5.8 — 02.08.2026

**Der Schalter kannte nur eine Richtung.** Die Ereignisbehandlung entsteht einmal beim
Aufbau und hält das `p` von genau diesem Durchlauf fest; spätere Aktualisierungen erzeugen
ein neues. Die Beschriftung wechselte deshalb brav zwischen *Ein-* und *Ausschalten*, der
Klick schickte aber immer die Richtung vom ersten Zeichnen — im Protokoll dreimal
`turn_off` und kein einziges `turn_on`. Der aktuelle Stand hängt jetzt am Element statt im
Abschluss. ⚠ Aufgefallen ist es erst an der zweiten Matrix: die erste schaltet über ein
Skript, und ein Skript kennt keine Richtung.

**Der Schalter steht wieder vor dem Regler.** Kam er nachträglich dazu — weil das Tor beim
ersten Zeichnen noch nicht eingetragen war —, landete er hinter dem Helligkeitsregler und
die Karten sahen unterschiedlich aus. `prepend` statt `appendChild`.

**★ Nach dem Einschalten wird ein Vollbild erzwungen.** WLED stellt beim Einschalten seinen
eigenen letzten Zustand her — je nach Voreinstellung eine Farbe oder ein Effekt. Die App
wusste davon nichts und schickte nur die Unterschiede zu dem Bild, das *sie* zuletzt
gesendet hatte; auf der Matrix blieb alles stehen, was sie nicht selbst gezeichnet hatte.
Am Gerät erlebt: nach dem Einschalten war die Fläche komplett rot und blieb es, bis das
nächste turnusmäßige Vollbild fiel — bei `full_frame_every: 60` und 5 s Takt bis zu fünf
Minuten. Betrifft auch das Einschalten aus Home Assistant heraus, nicht nur über den Knopf
in der App.

## 0.5.7 — 02.08.2026

**Ein `gate:` oder `brightness:` ließ sich bei einer Anzeige, die noch keines hatte, gar
nicht eintragen.** `setze()` lief die Pfadstufen entlang, ohne fehlende anzulegen — die
Zuweisung warf dann einen TypeError und die Eingabe verschwand **wortlos**. Getroffen hat
es genau die frisch angelegten Anzeigen; wer eine mit vorhandenem Block bearbeitete, merkte
nie etwas davon. Fehlende Stufen werden jetzt angelegt (Liste bei einem Zahlen-Index, sonst
Zuordnung); beim *Leeren* eines Feldes wird bewusst nichts angelegt, sonst entstünden leere
Zweige in der Datei.

## 0.5.6 — 02.08.2026

**Der Helligkeitsregler fehlte bei jeder Anzeige ohne `gate:`-Block.** Schalter und Regler
steckten in einem gemeinsamen `if (… && p.schaltbar)` — wer keinen Tor-Eintrag hat, bekam
also auch keinen Regler, obwohl die Helligkeit mit dem Tor nichts zu tun hat (die
Begleit-Integration legt dafür ohnehin eine eigene `number`-Entität an). Beide werden jetzt
getrennt aufgebaut, jeder mit eigenem Merker. Nebeneffekt: taucht ein Tor später auf, weil
das Gerät stromlos war, kommt der Schalter nachträglich dazu statt bis zum Neuladen der
Seite zu fehlen.

## 0.5.5 — 02.08.2026

**Kein Scrollbalken mehr unter dem Vorschaubild.** Das Bild hat `max-width: 100%` und
einen 1-px-Rahmen — mit der CSS-Vorgabe `content-box` zählt der Rahmen *zusätzlich*, das
Bild war also 2 px breiter als sein Behälter. `box-sizing: border-box` behebt es.

**Kein Zucken mehr beim Aktualisieren.** `img.src = neu` wirft das alte Bild sofort weg und
lädt erst danach; währenddessen hat das Element keine Größe, die Karte fällt zusammen und
alles darunter springt nach oben. Jetzt wird das neue Bild erst geholt und dann getauscht
— über einen Blob, weil die Antwort `Cache-Control: no-store` trägt und ein zweiter Zugriff
auf dieselbe Adresse eine zweite Übertragung wäre. Scheitert das Holen, bleibt das alte
Bild stehen.

**Geräte lassen sich jetzt löschen.** Die Begleit-Integration hatte kein
`async_remove_config_entry_device` — Home Assistant bot das Löschen deshalb gar nicht erst
an („Config entry does not support device removal"). Wer die Kennung einer Anzeige ändert
oder eine Anzeige entfernt, behielt das alte Gerät für immer in der Übersicht. Erlaubt wird
das Löschen genau dann, wenn die App die Anzeige nicht mehr kennt; ein Gerät zu einer
laufenden Anzeige bleibt geschützt.

⚠ **Zur Kennung einer Anzeige:** sie bildet `unique_id` und Geräte-Kennung. Wird sie
geändert, legt HA einen **kompletten zweiten Satz** Entitäten an und der alte bleibt als
`unavailable` liegen — samt allem, was daran hängt (Dashboard-Karten, Firmware mit fest
eingetragener Entity-ID). Der **Name** ist dagegen frei änderbar: die Entity-ID entsteht
einmal beim Anlegen und bleibt danach stehen.

## 0.5.4 — 02.08.2026

**Die Karte einer gelöschten oder umbenannten Anzeige blieb im Betriebs-Reiter stehen.**
Karten werden über `p-<kennung>` wiedererkannt und wurden nur angelegt, nie entfernt — wer
die Kennung änderte, sah die alte Karte weiter, mit eingefrorenen Werten. Sie wird jetzt
weggeräumt. Nebenbei folgt die Reihenfolge der Karten wieder der Beschreibungsdatei, auch
nach einem Umsortieren.

**Neu: `led_pitch` je Anzeige** — das Rastermaß der Matrix in Millimetern (P3 = 3,0).
Wirkt nur auf die Darstellung, nie auf das Gesendete: die Vorschau wird darauf bezogen
skaliert, sodass zwei Anzeigen im echten Größenverhältnis nebeneinander stehen, und die
LEDs werden als Punkte gezeichnet statt als aneinanderstoßende Quadrate. Ohne Eintrag
ändert sich nichts.

Vergrößern, Gitter und Punkte liegen jetzt in **einer** Funktion, die Betriebs-Reiter und
Konfigurator gemeinsam benutzen — vorher stand derselbe Ablauf an zwei Stellen, genau die
Doppelung, vor der der Kommentar an `pixelraster` schon warnte.

⚠ Dabei zwei Fallen vermieden, die beide erst beim Messen auffielen: der Konfigurator
schrieb den *tatsächlich benutzten* Zoom zurück in den *angeforderten* — mit `led_pitch`
wäre das Bild bei jedem Durchlauf weiter geschrumpft (6 → 5 → 4 → 3). Und ein Tippfehler
in `led_pitch` oder `interval` ergab einen nackten `ValueError` statt der Meldung mit
Pfad; beide gehen jetzt durch `_float` und melden `panels[0].led_pitch: muss eine Zahl
sein, ist 'drei'`.

## 0.5.3 — 02.08.2026

**Der Konfigurator zeigte immer die erste Anzeige.** Beim Wechsel auf eine zweite Matrix
blieb das Vorschaubild der ersten stehen. Zwei Ursachen, beide erst mit der zweiten
Anzeige sichtbar:

- `K.panelIndex` stand seit jeher auf `0` und wurde **nie wieder gesetzt** — Vorschau und
  Kachelraster bezogen sich damit dauerhaft auf `panels[0]`. Der Wert wird jetzt aus der
  Auswahl im Baum **abgeleitet** statt gemerkt; ein Zustand, den man vergessen kann
  nachzuführen, ist ein Zustand zuviel.
- `waehle()` holte die Vorschau nur neu, wenn sich die *Screen-Vorwahl* änderte. Ein
  Wechsel der Anzeige löste gar nichts aus. Jetzt wird auch darauf geprüft.

Das Raster beim Ziehen von Kacheln hing an derselben Stelle und stimmt damit ebenfalls
wieder.

## 0.5.2 — 02.08.2026

**Eine weitere Anzeige lässt sich jetzt im Konfigurator anlegen.** Bisher ging das nur in
der Beschreibungsdatei: der Baum legte für Kacheln, Screen-Gruppen und Screens einen
Hinzufügen-Pfad an, für die Anzeige selbst fehlte er. Der Knopf `+ Anzeige` steht unten im
Formular einer Anzeige — und unter *Vorgaben*, damit man auch dann herankommt, wenn noch
gar keine existiert.

Die neue Anzeige übernimmt Größe, Raster, Takt und `clear_segments_to` von der ersten
vorhandenen. **`host` bleibt absichtlich leer:** eine erfundene Adresse wäre schlimmer als
keine, weil die Anzeige dann still ins Leere sendet oder an ein fremdes Gerät gerät.

**Dazu wurde ein Loch in der Prüfung geschlossen.** `_pflicht` sah nur nach, ob ein
Schlüssel *vorhanden* ist — `host: ''` kam also durch und wäre erst im Betrieb als Anfrage
an `http:///json/state` aufgefallen. Leere Zeichenketten in Pflichtfeldern werden jetzt
abgewiesen (`panels[1]: 'host' ist leer`). An der bestehenden Beschreibung ändert sich
nichts, gegengeprüft.

**Der Betriebs-Reiter stellt mehrere Anzeigen nebeneinander**, sobald der Schirm breit
genug ist, und fällt auf schmalen Geräten von selbst wieder auf eine Spalte zurück. Die
560 px Mindestbreite sind gerechnet: die Vorschau kommt mit `zoom=6`, eine 128er Matrix ist
damit 768 px breit — bei schmaleren Spalten würde die Pixelgrafik sichtbar weich. Bei nur
einer Anzeige ändert sich nichts.

## 0.5.1 — 02.08.2026

**Sicherungen liegen nicht mehr in `/config`.** Beim Speichern landet die Kopie jetzt im
Unterordner `matrix_panel_sicherungen/` neben der Beschreibungsdatei. Bisher lagen sie
direkt daneben und haben den Dateibrowser von Home Assistant zugemüllt. Die Rotation gab
es schon (die letzten 20 bleiben liegen), sie war nur nie sichtbar — mit 16 Dateien war
die Grenze schlicht noch nicht erreicht. Sicherungen aus früheren Fassungen holt die App
beim Start selbst in den Ordner, sonst würde die Aufräumung sie nie wieder finden.

**Die rote Meldung „nicht erreichbar" blieb stehen, solange die Anzeige aus war.**
Gelöscht wurde `letzter_fehler` nur von einem erfolgreich gesendeten Bild — und gesendet
wird bei ausgeschalteter Anzeige gerade nicht. Beim Ausschalten läuft typischerweise noch
ein Block in die Zeitüberschreitung, und genau der eine Sendefehler hing danach als
Dauerwarnung fest. Jetzt wird die Meldung weggenommen, sobald die Anzeige bewusst aus ist;
der kumulative Zähler bleibt. Dazu blendet die Oberfläche die Marke „nicht erreichbar" bei
ausgeschalteter Anzeige aus — sie sagt dort nichts, was „Anzeige aus" nicht schon sagt.

## 0.5.0 — 01.08.2026

**An/Aus und Helligkeit im Betriebs-Reiter.** Ein Schalter und ein Regler über den
Screen-Wählern.

Der Schalter ruft, was in `gate.script` steht — ohne Eintrag schaltet die App das Tor
direkt. Das Skript ist dort nötig, wo mehr passieren muss als Strom an: warten bis der
Controller gebootet ist, HAs Konfigurationseintrag aktivieren, danach ein Vollbild. Diese
Reihenfolge gehört nicht in eine Render-App.

★ Dabei einen stillen Fehler gefunden: `setze_helligkeit` schrieb nur einen app-internen
Wert. Gelesen wird der aber ausschließlich, wenn **keine** `brightness.entity`
konfiguriert ist — mit einer konfigurierten Entität war der Regler also wirkungslos, ohne
dass irgendwo etwas schiefging. Jetzt schreibt er auf die Entität (`input_number`/`number`
über `set_value`).

Dafür kann die HA-Anbindung erstmals auch **schreiben** (`call_service` über den
WebSocket). Bewusst eng gehalten: eine Entität, ein Dienst, keine freie Nutzlast von außen.
Die Domain kommt aus der Entitäts-ID und ist nicht fest verdrahtet.

## 0.4.1 — 01.08.2026

**Kein Flackern mehr alle paar Minuten.** Das Vollbild leerte die Fläche vorher
ausdrücklich und baute sie dann in mehreren Anfragen wieder auf — dazwischen war die
Matrix dunkel. Jetzt kodiert das Vollbild auch die schwarzen Läufe mit und beschreibt
damit die ganze Fläche, statt sie nur zu ergänzen. Das Leeren fällt ersatzlos weg, und
kein Pixel wird mehr dunkel: jedes wird an Ort und Stelle überschrieben.

Der Wiederaufsetzpunkt bleibt erhalten — ein Pixel, das nicht dorthin gehört, wird jetzt
ausdrücklich schwarz überschrieben statt durch Leeren entfernt.

Preis, am echten Bild gemessen (8192 Pixel, 6803 davon schwarz): 4782 statt 2535 Werte,
34 statt 18 kB JSON, 7 statt 4 Blöcke — alle fünf Minuten, im Mittel rund 54 Byte je
Sekunde.

## 0.4.0 — 01.08.2026

**Symbol-Editor.** Neuer Reiter *Symbole*: Pixel malen, speichern, fertig. Stift,
Radiergummi, Pipette, Alles füllen/leeren, 40 Schritte Rückgängig, Palette plus freier
Farbwähler, fünf Größen (8×8 bis 32×8). Mitgelieferte Symbole lassen sich öffnen und unter
demselben Namen überschreiben; Löschen gibt das mitgelieferte wieder frei.

**Mit Alphakanal** — und das ist kein Beiwerk: bei den eingebauten Symbolen ist Schwarz
durchsichtig, eine schwarze Fläche kann man dort gar nicht malen. Eine eigene PNG-Datei
kann beides. Deshalb ist die Deckkraft von der Farbe getrennt, und durchsichtige Pixel
zeigt das Raster als Schachbrett.

Gespeichert wird nach `/config/matrix_icons`. Die laufende Anzeige übernimmt das
**sofort**: die Symbolverwaltung liest sich selbst neu ein, statt ersetzt zu werden — die
Anzeigen behalten dadurch Handauswahl und laufende Meldungen.

## 0.3.0 — 01.08.2026

**Konfigurator.** Alles, was in der Beschreibungsdatei stehen kann, lässt sich jetzt in
der Oberfläche anlegen und ändern — Reiter *Konfiguration* neben *Betrieb*.

- **Struktur** links: der ganze Baum, ein- und ausklappbar, mit Lage je Kachel.
- **Vorschau** in der Mitte: Kacheln anklicken **und ziehen**. Raster-Kacheln rasten in
  Zellen ein und behalten ihr `cell`, absolut platzierte gehen pixelweise und behalten ihr
  `at` — aus einem `cell` wird nie stillschweigend ein `at`. Meldezeile und Bereich einer
  Screen-Gruppe erscheinen gestrichelt in Gelb und lassen sich ebenso verschieben.
- **Formulare** rechts, erzeugt aus derselben Beschreibung, gegen die auch geprüft wird.
  Entitäten werden mit ihrem aktuellen Wert vorgeschlagen, Symbole als Bildergitter
  gezeigt, Symbol und Farbe in allen vier Formen einstellbar (fest, `map`, `steps`,
  `template`).
- **Anlegen** über ein `+` am Zweig im Baum; Umsortieren, Duplizieren, Löschen im Formular.
- **Schriftregeln** (`fonts:`) mit sichtbarem Unterschied zwischen eingebauter Vorgabe und
  eigenem Eintrag.
- **Zwei Sprachen** (Deutsch, Englisch); eine weitere ist eine JSON-Datei in `www/i18n/`.

Die Kommentare in der YAML überleben das Speichern: geändert wird in die vorhandene
Struktur hinein (ruamel im Round-Trip-Modus), unveränderte Stellen werden nicht angefasst.
Vor jedem Schreiben eine Sicherung, die letzten 20 bleiben liegen. Wer die Datei nebenher
im Editor ändert, bekommt eine Warnung statt eines stillen Überschreibens.

⚠ **Ein Fehler in der Anzeige, den erst der Konfigurator sichtbar gemacht hat:**
`map: {off: dry, on: wet}` wurde von `yaml.safe_load` zu `{False: 'dry', True: 'wet'}` —
YAML 1.1 macht aus `on`/`off` Wahrheitswerte. Der Zustand einer HA-Entität ist aber die
Zeichenkette `"off"`, der Vergleich schlug also immer fehl und still griff der `default`.
Auf der Matrix hieß das: bei trockenem Wetter dauerhaft das Regensymbol. Aufgefallen ist
es nur, weil der Konfigurator (ruamel, YAML 1.2) ein anderes Symbol zeichnete als die
laufende Anzeige. Die Datei wird jetzt so gelesen, dass `on/off/yes/no` Zeichenketten
bleiben; `true`/`false` bleiben Wahrheitswerte.

Weiter behoben:

- **Neu laden** baut Schriften und Symbole mit neu auf. Vorher blieb eine neue Datei in
  `matrix_icons` unsichtbar und eine Änderung an `fonts:` wirkungslos, bis jemand die
  ganze App neu startete.
- Die **Ausdehnung** einer Kachel ist die Vereinigung von Symbolkasten und Textfeld, nicht
  die Rasterzelle — eine Kachel mit eigenem `text_width` wurde sonst halb markiert.
- Der **Browser** zeigte nach einer Aktualisierung die alte Oberfläche: die statischen
  Dateien kamen ohne `Cache-Control`, und die Seite verwies ohne Kennung darauf. Jetzt
  hängt an den Verweisen die Änderungszeit, und `/static/` antwortet mit `no-cache`.

## 0.2.0 — 31.07.2026

**MQTT ist raus.** Die Bedienelemente in Home Assistant kommen jetzt von einer
Begleit-Integration (`custom_components/matrix_panel`, HACS-fähig), die mit der App über
deren HTTP-Schnittstelle spricht.

Grund: über den Supervisor-Dienst `mqtt` kam die App nur an einen Broker, der als App
läuft. Wer einen **externen** Broker betreibt, bekam „MQTT nicht verfügbar" — obwohl MQTT
da war. Und wer MQTT gar nicht nutzt, hätte es allein für die Matrix einführen müssen.

Dafür gibt es jetzt:

- ein **Gerät** je Anzeige statt loser Entitäten, mit Diagnose-Rubrik
- eine **Vorschau als `image`-Entität** — das Matrixbild aufs Dashboard
- echte **Dienste** `matrix_panel.notify` / `.notify_clear` mit Feldern und Auswahllisten,
  statt einer JSON-Nutzlast auf einem Topic
- **Selbstanmeldung**: die App meldet sich beim Supervisor an, HA bietet die Integration
  von selbst zur Einrichtung an. Host und Port kommen mit.

Ohne die Integration läuft die App weiter; bedient wird dann über ihre eigene Oberfläche.

⚠ Fallen, die dabei aufgefallen sind und im Code stehen:

- **`GET /discovery` ist Apps nicht erlaubt** (401), `POST` schon. Ein Aufräumen alter
  Anmeldungen über die Liste scheitert — und ist unnötig, der Supervisor dedupliziert
  selbst.
- **Beim Beenden wird nicht abgemeldet.** HA entfernt zu einer gelöschten Anmeldung unter
  Umständen den Konfigurationseintrag; bei jedem App-Neustart die Einrichtung wegzuwerfen
  wäre ein schlechter Tausch.

## 0.1.1 — 31.07.2026

Zwei Schönheitsfehler aus 0.1.0, beide vom User bemerkt:

- `panel_icon` stand auf `mdi:dot-grid` — **diesen Icon-Namen gibt es nicht** (gegen die
  MDI-Quelle geprüft: 404, richtig ist `mdi:dots-grid`). In der Seitenleiste blieb der
  Platz vor dem Namen deshalb leer.
- `url` zeigte auf einen erfundenen Host statt auf den echten — betraf
  `config.yaml` und `repository.yaml`.

⚠ Merke fürs nächste Mal: eine geänderte `config.yaml` wird bei einer INSTALLIERTEN App
weder von `ha apps reload` noch von `ha apps rebuild` übernommen — der Supervisor hält
seine eigene Kopie. Es braucht eine **Versionserhöhung** und `ha apps update`.

## 0.1.0 — 31.07.2026

Erste Fassung. **Seit 31.07.2026 produktiv** auf der Wohnzimmer-Matrix; der
pyscript-Renderer ist abgelöst und stillgelegt.

- YAML-Beschreibung: Anzeige → Grundbild → Screen-Gruppen mit Auslösern
- Bildaufbau mit Pillow, Differenzübertragung an WLED, Vollbild als Wiederaufsetzpunkt
- Schriften: eingebaute 5x3, dieselbe als BDF, Spleen und Terminus mitgeliefert
- Symbole der bisherigen Anlage unverändert übernommen, PNG-Symbole zusätzlich möglich
- MQTT-Discovery: Auswahl je Screen-Gruppe, Diagnose, Vollbild-Knopf, Helligkeit
- Live-Vorschau über Ingress
- Benachrichtigungszeile mit Balken bzw. WLED-Laufschrift

### Gemessen, nicht behauptet

**Vor dem Umschalten, rechnerisch:** `tools/parity_check.py` — 0 von 8192 Pixeln
Abweichung gegenüber dem pyscript-Renderer, in vier Fällen (Automatik, Handauswahl,
kurze und lange Benachrichtigung). `tools/check_5x3_bdf.py` — 87/87 Zeichen und
25/25 Kacheltexte gleich.

**Nach dem Umschalten, am Gerät:** sechs Vergleiche der App-Vorschau gegen das per
WLED-WebSocket ausgelesene Panel — jeweils **0 Struktur-Abweichungen**, in beiden
Screen-Stellungen. Diagnose im Betrieb: 206 Bytes je Bild, 13 geänderte Pixel,
0 Sendefehler.

⚠ Farben lassen sich dabei **nicht** direkt vergleichen: WLEDs Live-Vorschau liefert
die Werte nach Helligkeits- und Gammakorrektur (bei Helligkeit 23 wird aus `ffffff`
ein `5d5d5d`). Verglichen wird, welche Pixel leuchten.

### Beim Umschalten gefunden und behoben

- **s6 startet Dienste mit leerer Umgebung** — ohne `#!/usr/bin/with-contenv bash`
  bekam die App kein `SUPERVISOR_TOKEN`; das sah aus wie kaputte Zugangsdaten
  (MQTT 401, HA-Socket `auth_invalid`).
- **paho-mqtt 2.x** liefert im `on_connect` ein `ReasonCode`-Objekt, keine Zahl.
- **Der Vollbild-Anker war nie einer**: WLED leert ein Segment beim `i`-Schreiben nur,
  solange es nicht eingefroren ist — die Bildfläche läuft mit `frz: true`. Ein
  fälschlich leuchtendes Pixel blieb dadurch für immer stehen (am Gerät über
  14 Minuten und mehrere Anker hinweg nachgewiesen). Behoben durch einen
  Bereichseintrag `[0, W*H, "000000"]` vor den hellen Läufen; danach verschwand das
  hängengebliebene Pixel beim ersten Vollbild.
