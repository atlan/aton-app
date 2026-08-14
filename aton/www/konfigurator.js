/* Konfigurator — Formulare aus dem Schema, Kacheln auf der Vorschau.
 *
 * Grundsatz: die Oberflaeche rechnet NICHTS selbst nach, was der Server schon weiss.
 * Die Feldliste kommt aus /api/schema (derselben Beschreibung, gegen die geprueft wird),
 * und wo eine Kachel liegt, sagt /api/config/preview — sonst klickt man irgendwann daneben,
 * weil hier anders gerechnet wird als beim Zeichnen.
 */
'use strict';

const K = {
  daten: null, mtime: null, schema: null, texte: {}, sprache: 'de', sprachen: [],
  auswahl: null,          // Pfad als Array, z.B. ['panels',0,'widgets',3]
  kacheln: [],
  // ⚠ Zwei Zoomwerte, und das mit Absicht:
  //   `zoomWunsch` ist, was die Oberflaeche ANFORDERT — bleibt fest.
  //   `zoom` ist, was der Server tatsaechlich benutzt hat; damit werden Klick- und
  //   Ziehwege in Matrixpixel umgerechnet.
  // Bei gesetztem `led_pitch` weichen sie voneinander ab. Wuerde man wie frueher den
  // benutzten Wert zurueck in den angeforderten schreiben, schrumpfte das Bild bei jedem
  // Durchlauf weiter (6 -> 5 -> 4 -> ...) — eine Rueckkopplung, die man erst nach
  // mehreren Aktualisierungen bemerkt.
  zoomWunsch: 6, zoom: 6, groesse: [128, 64],
  // ⚠⚠ DRITTE Groesse neben den zwei Zoomwerten: wie stark der BROWSER das Bild
  // zusaetzlich verkleinert hat. `.k-buehne img` hat `max-width: 100%`, und sobald die
  // mittlere Spalte schmaler ist als Matrixbreite x Zoom (bei 128 px und Zoom 6 also
  // 768 px), rechnet der Browser das Bild herunter. Die Kachelrahmen wurden aber weiter
  // in ungerechneten Zoom-Pixeln gesetzt — sie standen dann breiter als das Bild und
  // ragten sichtbar ins Formular daneben. Am 07.08.2026 bei 1400 px Fensterbreite
  // gemessen: Buehne 715 px breit, Inhalt 770 px, sechs Elemente ueber dem Rand.
  skala: 1,
  schmutzig: false, symbole: [], schriften: [],
  // Seiten-Knoten, die schon einmal von selbst aufgeklappt wurden. ⚠ Ohne dieses
  // Gedaechtnis liesse sich eine Seite nie wieder ZUklappen: das automatische Aufklappen
  // wuerde bei jedem Neuzeichnen erneut greifen.
  seitenAuf: new Set(),
};

const T = (schluessel) => K.texte[schluessel] || schluessel;

/* Welche Anzeige gerade gemeint ist — abgeleitet aus der Auswahl im Baum.
 *
 * ⚠ Hier stand bis 0.5.3 ein Feld `K.panelIndex: 0`, das nach dem Anlegen NIE wieder
 * gesetzt wurde. Vorschau und Raster bezogen sich damit immer auf die ERSTE Anzeige,
 * egal was man anklickte. Solange es nur eine gab, konnte das niemand bemerken —
 * genau die Sorte Fehler, die mit der zweiten Anzeige schlagartig sichtbar wird.
 * Deshalb jetzt abgeleitet statt gemerkt: ein Zustand, den man vergessen kann
 * nachzufuehren, ist ein Zustand zuviel.
 */
function panelIndex() {
  const a = K.auswahl;
  if (a && a[0] === 'panels' && typeof a[1] === 'number') return a[1];
  return 0;
}
const el = (tag, klasse, text) => {
  const e = document.createElement(tag);
  if (klasse) e.className = klasse;
  if (text !== undefined) e.textContent = text;
  return e;
};

/* --- Pfad-Werkzeug ------------------------------------------------------ */
function hole(pfad) {
  let k = K.daten;
  for (const t of pfad) { if (k === undefined || k === null) return undefined; k = k[t]; }
  return k;
}
function setze(pfad, wert) {
  const loeschen = (wert === undefined || wert === '' || wert === null);
  let k = K.daten;
  for (let i = 0; i < pfad.length - 1; i++) {
    const t = pfad[i];
    if (k[t] === undefined || k[t] === null) {
      // ⚠ Fehlende Zwischenstufe ANLEGEN. Vorher lief die Schleife hier auf `undefined`
      // und die Zuweisung unten warf einen TypeError — die Eingabe verschwand WORTLOS.
      // Getroffen hat es genau die Faelle, in denen ein Zweig noch gar nicht existiert:
      // `gate:` oder `brightness:` bei einer frisch angelegten Anzeige. Wer eine Anzeige
      // mit vorhandenem Block bearbeitete, merkte nie etwas davon.
      if (loeschen) return;   // beim Leeren nichts anlegen, sonst entstehen leere Zweige
      // Ist der naechste Schritt eine Zahl, ist die Stufe eine Liste, sonst eine Zuordnung.
      k[t] = typeof pfad[i + 1] === 'number' ? [] : {};
    }
    k = k[t];
  }
  const letzter = pfad[pfad.length - 1];
  if (loeschen) delete k[letzter];
  else k[letzter] = wert;
  K.schmutzig = true;
  kopfAktualisieren();
}
const gleich = (a, b) => a && b && a.length === b.length && a.every((v, i) => v === b[i]);

/* --- Laden -------------------------------------------------------------- */
async function laden(sprache) {
  const s = await (await fetch('api/schema' + (sprache ? '?lang=' + sprache : ''))).json();
  K.schema = s.schema; K.texte = s.texte; K.sprache = s.sprache; K.sprachen = s.sprachen;
  K.stand = s.stand || '';
  // ⚠ Kommt vom Server (neueste Aenderungszeit der eigenen Symbole), nicht als Zaehler
  // bei null. Sonst zeigt der Konfigurator nach einem Neuladen der Seite weiter das alte
  // Bild aus dem Zwischenspeicher — gezeichnet wurde ja im Editor, nicht hier.
  K.symbolMarke = s.symbolmarke || 0;
  const c = await (await fetch('api/config')).json();
  K.daten = c.daten; K.mtime = c.mtime; K.pfad = c.pfad;
  K.symbole = (await (await fetch('api/icons')).json()).symbole;
  const sd = await (await fetch('api/fonts')).json();
  K.schriften = sd.schriften;
  K.schriftVorgaben = sd.eingebaut || {};
  /* Der Server hat veraltete Namen schon im Datenmodell umgeschrieben — in der DATEI
     stehen sie noch. Das IST eine ungespeicherte Aenderung, und sie muss auch so heissen:
     der Speichern-Knopf haengt an `K.schmutzig` (`disabled = !K.schmutzig`). Ohne diese
     Zeile bliebe er aus, und die Umbenennung waere erst zu schreiben, wenn zufaellig
     etwas anderes geaendert wird — der Hinweis unten waere ein Versprechen ohne Knopf. */
  K.schmutzig = !!(c.umbenannt && c.umbenannt.length);
  statischeTexte();
  zeichneAlles();
  vorschauHolen();
  meldungZeigen(c.umbenannt, 'ui.namen_beim_speichern');
}

/* Liste umbenannter Stellen in die Meldungszeile — gekuerzt, damit eine Datei mit
   zwanzig alten Schluesseln nicht die halbe Oberflaeche belegt. */
function meldungZeigen(liste, schluessel) {
  if (!liste || !liste.length) return;
  const m = document.getElementById('k-meldung');
  if (!m) return;
  const zeigen = liste.slice(0, 5).join(' · ');
  const rest = liste.length > 5 ? ` (+${liste.length - 5})` : '';
  m.className = 'k-meldung';
  m.textContent = `${T(schluessel)} ${zeigen}${rest}`;
}

function zeichneAlles() { kopfAktualisieren(); baumZeichnen(); formularZeichnen(); }

/* --- Kopfzeile ---------------------------------------------------------- */
function kopfAktualisieren() {
  const k = document.getElementById('k-kopf');
  k.innerHTML = '';
  const pfad = el('span', 'host', K.pfad || '');
  const wachs = el('span', 'k-wachs');
  k.append(pfad, wachs);

  if (K.schmutzig) {
    const m = el('span', 'marke k-marke-warn', T('ui.ungespeichert'));
    k.append(m);
  }
  const sprachwahl = el('select');
  K.sprachen.forEach(s => {
    const o = new Option(s.toUpperCase(), s);
    if (s === K.sprache) o.selected = true;
    sprachwahl.add(o);
  });
  sprachwahl.onchange = () => laden(sprachwahl.value);
  sprachwahl.title = T('ui.sprache');

  const pruefen = el('button', 'k-knopf', T('ui.pruefen'));
  pruefen.onclick = pruefenLassen;
  const einlesen = el('button', 'k-knopf', T('ui.einlesen'));
  einlesen.title = T('ui.einlesen_hilfe');
  einlesen.onclick = neuEinlesen;
  const speichern = el('button', 'k-knopf k-haupt', T('ui.speichern'));
  speichern.onclick = speichernLassen;
  speichern.disabled = !K.schmutzig;
  const verwerfen = el('button', 'k-knopf', T('ui.verwerfen'));
  verwerfen.onclick = () => laden(K.sprache);
  k.append(sprachwahl, pruefen, einlesen, verwerfen, speichern);
}

/* Beschreibung UND Register serverseitig neu einlesen — Schriften, Symbole und die
   eigenen Widget-Typen aus /config/aton_widgets.

   ⚠⚠ Ohne diesen Knopf war eine frisch abgelegte Plugin-Datei nur ueber einen NEUSTART
   der App zu bekommen: serverseitig werden die Register sonst allein beim Start und beim
   Speichern neu gelesen. Und selbst danach blieb der neue Typ unsichtbar, weil die Seite
   ihr Schema seit dem Aufbau festhaelt — deshalb hier BEIDES, erst der Server, dann die
   Seite. Genau diese Kombination hat einmal eine halbe Stunde gekostet.

   ⚠ `laden()` holt auch die Beschreibung neu und verwirft dabei ungespeicherte
   Aenderungen — daher dieselbe Rueckfrage wie beim Veraltet-Knopf. */
async function neuEinlesen() {
  if (K.schmutzig && !confirm(T('ui.ungespeichert_neu_laden'))) return;
  let a;
  try {
    a = await (await fetch('api/reload', { method: 'POST' })).json();
  } catch (e) {
    a = { ok: false };
  }
  await laden(K.sprache);
  const m = document.getElementById('k-meldung');
  m.style.display = '';
  m.className = 'k-meldung ' + (a.ok ? 'k-gut' : 'k-fehler');
  m.textContent = a.ok ? '✓' : T('ui.einlesen_abgelehnt');
}

/* --- Baum --------------------------------------------------------------- */
/* Eingeklappt startet alles ausser der obersten Ebene: die Beschreibung hat schnell
   fuenfzig Kacheln, und eine Liste, die nicht auf den Schirm passt, ist keine Struktur. */
K.offen = new Set(['defaults', 'panels']);
const schluessel = (pfad) => pfad.join('/');

function baumZeichnen() {
  const ziel = document.getElementById('k-baum');
  ziel.innerHTML = '';
  const wurzel = el('ul');

  /* ⚠⚠ HIER wird NICHTS aufgeklappt. Der Pfad zur Auswahl geht einmalig in `waehle()` auf
     — beim Klick, nicht bei jedem Zeichnen.

     Vorgeschichte, zweimal am selben Tag falsch repariert: die Schleife stand hier und
     trug den Pfad der Auswahl bei JEDEM Neuzeichnen wieder ein. Damit war jeder Knoten
     auf diesem Pfad unzuklappbar — `K.offen.delete(s)` im Pfeil wirkte, und Zeilen
     spaeter machte die Schleife es rueckgaengig. In 0.13.2 habe ich nur den Knoten SELBST
     ausgenommen (`i < laenge`); die ELTERN blieben verhaftet, und genau daran ist es dem
     Benutzer erneut aufgefallen: „Matrix Wohnzimmer Side" liess sich nicht schliessen,
     solange darin etwas ausgewaehlt war. Im Browser gemessen — `panels/0` stand nach dem
     Klick unveraendert in `K.offen`.

     Aufklappen ist eine Folge des AUSWAEHLENS, kein Zustand des Zeichnens. Wer das wieder
     hierher schiebt, nimmt dem Pfeil seine Wirkung. */

  wurzel.append(knoten(T('ui.vorgaben'), ['defaults']));
  const fo = K.daten.fonts || {};
  wurzel.append(knoten(T('ui.schriften'), ['fonts'],
                       String(Object.keys(fo).length)));

  (K.daten.panels || []).forEach((p, pi) => {
    const kinder = [];

    const wl = (p.widgets || []).map((w, wi) =>
      knoten(kachelName(w), ['panels', pi, 'widgets', wi], w.type || 'tile', lage(w)));
    kinder.push(knoten(T('ui.grundbild'), ['panels', pi, 'widgets'],
                       String((p.widgets || []).length), '', wl,
                       ['panels', pi, 'widgets']));

    const gl = (p.screen_groups || []).map((g, gi) => {
      const sl = (g.screens || []).map((sc, si) => {
        const spfad = ['panels', pi, 'screen_groups', gi, 'screens', si];
        const kacheln = (liste, basis) => (liste || []).map((w, wi) =>
          knoten(kachelName(w), basis.concat([wi]), w.type || 'tile', lage(w)));

        // Ein Screen mit `seiten:` bekommt eine Ebene mehr: die Seiten sind Fassungen
        // DESSELBEN Screens (in der Auswahl steht nur er), und ihre Kacheln liegen an
        // denselben Stellen — ohne eigene Ebene waeren sie im Baum nicht zu trennen.
        if (Array.isArray(sc.seiten)) {
          const pl = sc.seiten.map((se, sj) => {
            const ppfad = spfad.concat(['seiten', sj]);
            // ★ Beim ERSTEN Auftauchen von selbst aufklappen. Sonst klappt man einen
            // Screen auf und sieht nur Seitennamen — die Kacheln, um die es geht, waeren
            // eine Ebene tiefer versteckt. Vor den Seiten sassen sie direkt darunter,
            // und genau dieses Verhalten soll erhalten bleiben.
            const ps = schluessel(ppfad);
            if (!K.seitenAuf.has(ps)) { K.seitenAuf.add(ps); K.offen.add(ps); }
            return knoten(se.name || (T('ui.seiten') + ' ' + (sj + 1)), ppfad,
                          String((se.widgets || []).length), '',
                          kacheln(se.widgets, ppfad.concat(['widgets'])),
                          ppfad.concat(['widgets']));
          });
          return knoten(sc.name, spfad, sc.seiten.length + '\u00d7', '', pl,
                        spfad.concat(['seiten']));
        }
        return knoten(sc.name, spfad, String((sc.widgets || []).length), '',
                      kacheln(sc.widgets, spfad.concat(['widgets'])),
                      spfad.concat(['widgets']));
      });
      return knoten(g.name || g.id, ['panels', pi, 'screen_groups', gi], '', '', sl,
                    ['panels', pi, 'screen_groups', gi, 'screens']);
    });
    kinder.push(knoten(T('ui.screen_gruppen'), ['panels', pi, 'screen_groups'],
                       String((p.screen_groups || []).length), '', gl,
                       ['panels', pi, 'screen_groups']));
    /* Den alten Block NUR zeigen, solange er in der Datei steht. Frueher stand der Knoten
       immer da und legte den Block beim ersten Eintrag an — seit die Meldezeile eine
       Kachel ist, waere das ein Weg zurueck in die alte Schreibweise, den niemand sucht.
       Wer den Block hat, findet ihn weiter (samt Knopf zum Umwandeln). */
    if (p.notify) kinder.push(knoten(T('ui.notify'), ['panels', pi, 'notify']));

    wurzel.append(knoten(p.name || p.id, ['panels', pi], T('ui.anzeige'), '', kinder));
  });
  ziel.append(wurzel);
}

/* Beschriftung einer Kachel: das, woran man sie wiedererkennt. */
function kachelName(w) {
  /* Eine Meldezeile zeigt NIE den eigenen `text:` — ihr Text kommt aus der Meldung. Zu
     unterscheiden sind zwei Meldezeilen am Kanal, und nur an dem. Deshalb steht diese
     Zeile vor der Textabfrage: sonst stuende hier ein `text:`, den der Renderer ignoriert. */
  if (w.type === 'notify') return w.channel ? `notify:${w.channel}` : 'notify';
  if (w.text) return `“${w.text}”`;
  if (w.value) return w.value.replace(/^[a-z_]+\./, '');
  if (w.template) return (w.icon && typeof w.icon === 'string') ? w.icon : T('ui.vorlage');
  if (typeof w.icon === 'string') return w.icon;
  if (w.icon && w.icon.value) return w.icon.value.replace(/^[a-z_]+\./, '');
  if (w.image) return w.image;
  return w.type || 'tile';
}

/* Lage kompakt: Raster als [Zeile,Spalte], absolut als x,y */
function lage(w) {
  if (Array.isArray(w.cell)) return `[${w.cell[0]},${w.cell[1]}]`;
  if (Array.isArray(w.at)) return `${w.at[0]},${w.at[1]}`;
  return '';
}

/* Was ein neuer Eintrag mitbringen soll: gerade genug, dass er sofort etwas anzeigt
   und die Pruefung durchlaeuft — den Rest macht man im Formular. */
const GERUEST = {
  widgets: () => ({ type: 'tile', cell: [0, 0], icon: 'info', text: 'neu' }),
  screens: (n) => ({ name: 'screen' + (n + 1), widgets: [] }),
  seiten: (n) => ({ name: 'Seite ' + (n + 1), widgets: [] }),
  // `region` ist Pflicht. Ohne einen brauchbaren Vorschlag scheitert die Pruefung
  // sofort nach dem Anlegen — also den Bereich einer vorhandenen Gruppe uebernehmen,
  // sonst die ganze Anzeige.
  screen_groups: (n, pfad) => {
    const p = hole(pfad.slice(0, -1)) || {};
    const vorbild = (p.screen_groups || []).find(g => Array.isArray(g.region));
    const gr = p.size || K.groesse || [128, 64];
    return { id: 'gruppe' + (n + 1), name: 'Gruppe ' + (n + 1),
             region: vorbild ? vorbild.region.slice() : [0, 0, gr[0], gr[1]],
             screens: [{ name: 'screen1', widgets: [] }] };
  },
  // ⚠ `host` bleibt ABSICHTLICH leer. Eine erfundene Adresse waere schlimmer als gar
  // keine: die Anzeige sendet dann an ein fremdes Geraet oder laeuft in
  // Zeitueberschreitungen, und niemand sieht, dass da noch etwas fehlt. So stoesst die
  // Pruefung direkt darauf, weil `host` Pflichtfeld ist.
  //
  // Groesse und Raster vom ersten vorhandenen Panel uebernehmen — meist haengt die
  // zweite Matrix am selben Aufbau, und wer es anders braucht, aendert zwei Zahlen.
  panels: (n) => {
    const vorbild = (K.daten.panels || [])[0] || {};
    return {
      id: 'anzeige' + (n + 1),
      name: 'Anzeige ' + (n + 1),
      host: '',
      size: (vorbild.size || K.groesse || [128, 64]).slice(),
      interval: vorbild.interval || 5,
      full_frame_every: vorbild.full_frame_every || 60,
      clear_segments_to: vorbild.clear_segments_to || 32,
      grid: Object.assign({}, vorbild.grid || { row_height: 9, col_width: 32,
                                                icon_width: 8, gap: 1 }),
      widgets: [],
    };
  },
};

function anlegen(listenpfad) {
  const art = listenpfad[listenpfad.length - 1];
  let liste = hole(listenpfad);
  if (!Array.isArray(liste)) {          // Zweig gibt es noch gar nicht
    setze(listenpfad, []);
    liste = hole(listenpfad);
  }
  liste.push(GERUEST[art](liste.length, listenpfad));
  K.offen.add(schluessel(listenpfad));
  K.schmutzig = true;
  waehle(listenpfad.concat([liste.length - 1]));
  nachAenderung();
}

function knoten(beschriftung, pfad, typ, lageText, kinder, neuPfad) {
  const li = el('li');
  const s = schluessel(pfad);
  const d = el('div', 'k-knoten' + (gleich(pfad, K.auswahl) ? ' aktiv' : ''));

  if (kinder && kinder.length) {
    const pfeil = el('span', 'k-pfeil', K.offen.has(s) ? '\u25be' : '\u25b8');
    pfeil.onclick = (ev) => {
      ev.stopPropagation();
      K.offen.has(s) ? K.offen.delete(s) : K.offen.add(s);
      baumZeichnen();
    };
    d.append(pfeil);
  } else {
    d.append(el('span', 'k-pfeil'));
  }

  d.append(el('span', 'k-name', beschriftung));
  if (lageText) d.append(el('span', 'k-lage', lageText));
  if (typ) d.append(el('span', 'k-typ', typ));
  if (neuPfad) {
    const plus = el('span', 'k-plus', '+');
    plus.title = T('ui.hinzufuegen');
    plus.onclick = (ev) => { ev.stopPropagation(); anlegen(neuPfad); };
    d.append(plus);
  }
  d.onclick = (ev) => { ev.stopPropagation(); waehle(pfad); };
  li.append(d);

  if (kinder && kinder.length && K.offen.has(s)) {
    const ul = el('ul');
    kinder.forEach(k => ul.append(k));
    li.append(ul);
  }
  return li;
}

function waehle(pfad) {
  // Eine stehende Umzugswarnung gilt fuer die zuletzt verschobene Kachel — wer etwas
  // anderes anwaehlt, hat sie gelesen oder sie interessiert ihn nicht mehr.
  // ⚠ Reihenfolge beachten: `kachelVerschieben` ruft ERST `waehle`, setzt die Warnung
  // DANACH — sonst raeumte diese Zeile sie sofort wieder weg.
  K.umzugHinweis = '';
  // ⚠ Beide Ebenen vergleichen. Nur der Screen-Name reichte nicht: ein Wechsel zwischen
  // zwei Seiten DESSELBEN Screens aenderte ihn nicht, und die Vorschau blieb stehen.
  const stand = () => JSON.stringify([vorwahlAusAuswahl(), seitenVorwahlAusAuswahl()]);
  const vorher = stand();
  const vorherPanel = panelIndex();
  // Den ganzen Pfad aufklappen — sonst sucht man das Ausgewaehlte. Aber NUR HIER, beim
  // Auswaehlen: bei jedem Zeichnen liesse sich anschliessend kein Knoten des Pfades mehr
  // zuklappen (siehe `baumZeichnen`).
  for (let i = 1; i <= pfad.length; i++) K.offen.add(schluessel(pfad.slice(0, i)));
  K.auswahl = pfad;
  baumZeichnen();
  formularZeichnen();
  markiereKachel();
  // Zeigt die Auswahl auf einen anderen Screen, muss das Bild neu — die Markierung
  // allein wuerde auf Kacheln zeigen, die gar nicht gezeichnet sind.
  // ⚠ Und ebenso bei einem Wechsel der ANZEIGE: sonst bleibt beim Sprung auf die zweite
  // Matrix das Bild der ersten stehen. Fiel erst mit der zweiten Anzeige auf.
  if (stand() !== vorher || panelIndex() !== vorherPanel) {
    vorschauHolen();
  }
}

/* --- Vorschau ----------------------------------------------------------- */
/* ★ Welchen Screen soll die Vorschau zeigen?

   Ohne diese Ableitung rendert der Server IMMER den gerade automatisch faelligen
   Screen. Wer im Baum eine Screen-Gruppe anwaehlt, sieht dann nichts passieren — und
   die Kacheln des angewaehlten Screens tauchen auch nicht als Rechtecke auf, weil der
   Server nur den sichtbaren Screen ausgibt. Also: die Auswahl bestimmt die Vorwahl. */
function vorwahlAusAuswahl() {
  const a = K.auswahl;
  if (!a || a[0] !== 'panels' || a[2] !== 'screen_groups') return {};
  const panel = (K.daten.panels || [])[a[1]];
  const gruppe = panel && (panel.screen_groups || [])[a[3]];
  if (!gruppe) return {};
  const screens = gruppe.screens || [];
  // Gruppe selbst angewaehlt -> ihr erster Screen; sonst der angewaehlte.
  const sc = a[4] === 'screens' ? screens[a[5]] : screens[0];
  return sc && sc.name ? { [gruppe.id]: sc.name } : {};
}

/* ★ Und dasselbe eine Ebene tiefer: WELCHE SEITE des Screens?

   Genau der Fall, den die Ableitung darueber offen liess. Temperatur und Feuchte sind
   zwei `seiten` DESSELBEN Screens — fuer beide kam oben derselbe Screen-Name heraus, die
   Aenderungserkennung in `waehle` sah keinen Unterschied und holte kein neues Bild. Wer
   im Baum auf „Feuchte" klickte, sah unveraendert Temperaturen und hielt es fuer einen
   Fehler seiner Beschreibung; tatsaechlich entschied allein die Uhr im Renderer.

   Auch der Pfad einer KACHEL laeuft hier durch (…,'seiten',m,'widgets',n) — sonst
   sprAenge die Vorschau beim Anklicken einer Kachel auf die falsche Seite zurueck. */
function seitenVorwahlAusAuswahl() {
  const a = K.auswahl;
  if (!a || a[0] !== 'panels' || a[2] !== 'screen_groups') return {};
  const panel = (K.daten.panels || [])[a[1]];
  const gruppe = panel && (panel.screen_groups || [])[a[3]];
  if (!gruppe || a[4] !== 'screens' || a[6] !== 'seiten') return {};
  const j = Number(a[7]);
  return Number.isInteger(j) ? { [gruppe.id]: j } : {};
}

/* Welcher Zoom passt in die mittlere Spalte?
 *
 * ★ Der GRUND, das hier zu rechnen statt das Bild hinterher zu verkleinern: `max-width`
 * rechnet die Pixelgrafik weich. Eine Matrix ist aber genau das Gegenteil von weich —
 * bei krummen Faktoren (0,931) verschmieren die LED-Punkte zu Brei. Ein ganzzahliger
 * Zoom, vom Server so gerendert, bleibt scharf.
 *
 * ⚠⚠ Gerechnet wird aus der SPALTENBREITE, niemals aus dem zurueckgemeldeten Zoom.
 * Wer `K.zoomWunsch = p.zoom` schreibt, baut eine Rueckkopplung: bei gesetztem
 * `led_pitch` weicht der benutzte vom angeforderten Zoom ab, und das Bild schrumpft
 * dann bei jedem Durchlauf weiter (6 → 5 → 4 …). Die Spaltenbreite haengt nicht am
 * Bild (`minmax(320px, 1fr)`), also dreht sich nichts im Kreis.
 */
function zoomFuerSpalte() {
  const buehne = document.getElementById('k-buehne');
  const feld = buehne && buehne.closest('.k-feld');
  if (!feld) return K.zoomWunsch;
  const st = getComputedStyle(feld);
  const platz = feld.clientWidth - parseFloat(st.paddingLeft) - parseFloat(st.paddingRight);
  // Versteckter Reiter misst 0 — dann den bisherigen Wert behalten, der richtige kommt,
  // sobald die Konfiguration sichtbar wird.
  if (!(platz > 0)) return K.zoomWunsch;
  const breite = (K.groesse && K.groesse[0])
    || (((K.daten.panels || [])[panelIndex()] || {}).size || [128])[0] || 128;
  // 2 px fuer den Rahmen des Bildes abziehen, sonst passt es um Haaresbreite nicht.
  return Math.max(1, Math.min(12, Math.floor((platz - 2) / breite)));
}

/* Nach Groessenaenderungen: neuen Zoom holen, wenn er sich lohnt — sonst nur die
   Rahmen neu setzen. Ein Abruf je Aenderung, nicht je Pixel. */
let anpassZeit = null;
function vorschauAnpassen() {
  clearTimeout(anpassZeit);
  anpassZeit = setTimeout(() => {
    const z = zoomFuerSpalte();
    if (z !== K.zoomWunsch) { K.zoomWunsch = z; vorschauHolen(); }
    else if (K.kachelnSetzen) K.kachelnSetzen();
  }, 150);
}

/* Eine Meldung nur zum Ansehen — und NUR, solange eine Meldezeile angewaehlt ist.

   Eine Meldezeile ohne anliegende Meldung zeichnet nichts. Wer sie platziert, schoebe also
   ein unsichtbares Rechteck herum und saehe erst im Betrieb, ob es passt. Dauerhaft eine
   Beispielmeldung einzublenden waere das andere Extrem: dann stuende in der Vorschau
   staendig etwas, das es auf der Matrix gar nicht gibt. Deshalb an der Auswahl gebunden. */
function beispielMeldung() {
  const w = K.auswahl && hole(K.auswahl);
  const istBlock = K.auswahl && K.auswahl[K.auswahl.length - 1] === 'notify';
  if (!w || (w.type !== 'notify' && !istBlock)) return null;
  const m = { text: T('ui.beispielmeldung'), level: 'info' };
  // Mit Kanal, sonst zeigte ausgerechnet die angewaehlte Zeile die Meldung nicht.
  if (w.channel) m.channel = w.channel;
  if (w.show_levels) m.level = String(w.show_levels).split(',')[0].trim();
  return m;
}

async function vorschauHolen() {
  const panel = (K.daten.panels || [])[panelIndex()];
  if (!panel) return;
  K.zoomWunsch = zoomFuerSpalte();
  const antwort = await fetch('api/config/preview', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ daten: K.daten, panel: panel.id, zoom: K.zoomWunsch,
                           vorwahl: vorwahlAusAuswahl(),
                           seiten: seitenVorwahlAusAuswahl(),
                           notiz: beispielMeldung() }),
  });
  const p = await antwort.json();
  const meldung = document.getElementById('k-vorschau-meldung');
  if (!p.ok) {
    /* ⚠⚠ Ohne die naechsten zwei Zeilen blieb die Ablehnung UNSICHTBAR: das Element
       startet mit `display:none`, und der Zweig darunter ist der einzige, der das je
       aendert. Wer einen Entwurf baute, den der Loader ablehnt, sah deshalb einfach
       nichts — die Vorschau behielt stumm das alte Bild, und die Begruendung stand im
       DOM, wo sie niemand liest.

       ⚠ `display` allein reichte NICHT: bei einem hohen Panel steht die Vorschauspalte
       ueber die Fensterhoehe hinaus, und die Meldung war zwar eingeblendet, aber
       ausserhalb des Bildes. Deshalb steht sie jetzt ueber der Buehne (index.html) UND
       holt sich in den Blick — aber nur beim Wechsel von unsichtbar zu sichtbar, sonst
       ruckelt die Seite bei jedem Tastendruck im Formular. */
    const war_versteckt = meldung.style.display === 'none';
    meldung.className = 'k-meldung k-fehler';
    meldung.textContent = p.meldung || T('ui.fehler');
    meldung.style.display = '';
    if (war_versteckt) meldung.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    return;
  }
  /* Ladefehler eigener Widget-Typen kommen VOR den Renderfehlern: sie sind der Grund,
     warum ein Typ gar nicht erst existiert, und stuenden sonst nur im Protokoll — dort
     sucht sie niemand, der gerade ein Widget zusammenbaut. */
  const eigeneFehler = (K.schema && K.schema.widget_eigene_fehler) || [];
  const zeilen = eigeneFehler.concat(p.fehler || []);
  meldung.className = 'k-meldung' + (eigeneFehler.length ? ' k-fehler' : '');
  meldung.textContent = zeilen.join('\n');
  meldung.style.display = zeilen.length ? '' : 'none';

  K.kacheln = p.kacheln; K.zoom = p.zoom; K.groesse = p.groesse;
  const buehne = document.getElementById('k-buehne');
  buehne.innerHTML = '';
  const bild = el('img');
  bild.src = p.png;
  buehne.append(bild);

  /* Die Rahmen sitzen erst, wenn feststeht, wie gross das Bild WIRKLICH gezeichnet
     wurde — vorher ist `clientWidth` 0 und alles landet in der Ecke. */
  const kachelnSetzen = () => {
    // ⚠ `clientWidth` ist 0, solange der Reiter versteckt ist (`section[hidden]`).
    // Ohne diesen Rueckfall wuerde der Faktor 0 und ALLE Rahmen fielen auf Groesse
    // null zusammen — beim Bauen genau so passiert. Der richtige Wert kommt dann,
    // sobald der Reiter sichtbar wird (index.html ruft `K.kachelnSetzen` erneut).
    K.skala = (bild.naturalWidth && bild.clientWidth)
      ? bild.clientWidth / bild.naturalWidth : 1;
    const f = p.zoom * K.skala;
    [...buehne.querySelectorAll('.k-kachel')].forEach(e => e.remove());
    p.kacheln.forEach(kc => {
      const r = el('div', 'k-kachel' + (kc.feld === 'region' ? ' k-bereich' : '') +
                          (gleich(kc.pfad, K.auswahl) ? ' aktiv' : ''));
      r.style.left = (kc.x * f) + 'px';
      r.style.top = (kc.y * f) + 'px';
      r.style.width = (kc.w * f) + 'px';
      r.style.height = (kc.h * f) + 'px';
      r.title = `${kc.typ} @ ${kc.x},${kc.y} · ${kc.w}×${kc.h}`;
      ziehbarMachen(r, kc);
      buehne.append(r);
    });
  };
  bild.onload = kachelnSetzen;
  if (bild.complete && bild.naturalWidth) kachelnSetzen();

  /* ⚠⚠ Der Faktor haengt an `clientWidth`, und die steht erst fest, wenn der Browser das
     Bild gelegt hat. War sie beim Zeichnen noch 0, greift der Rueckfall `skala = 1` und
     ALLE Rahmen sitzen um denselben FAKTOR daneben — nicht um einen festen Versatz, sie
     driften also umso weiter, je weiter rechts und unten sie liegen.

     Bis hierher richtete das erst das naechste Fensterereignis: Groesse aendern,
     Reiterwechsel (index.html ruft `K.kachelnSetzen`). Am 08.08.2026 vom Benutzer
     gemeldet — die Kaesten sassen daneben und sprangen erst an ihren Platz, als sich das
     Fenster umlegte. Auf ein Ereignis zu warten, das mit der Sache nichts zu tun hat, ist
     die falsche Bedingung; ein Beobachter AM BILD merkt es selbst.

     ⚠ Nur bei tatsaechlich anderer Breite neu setzen. `kachelnSetzen` schreibt in dieselbe
     Buehne, und ein Beobachter, den die eigene Arbeit erneut ausloest, ist eine Schleife
     (der Browser meldet sie als „ResizeObserver loop completed…"). */
  if (K.bildBeobachter) K.bildBeobachter.disconnect();
  let gelegteBreite = bild.clientWidth;
  K.bildBeobachter = new ResizeObserver(() => {
    if (bild.clientWidth === gelegteBreite) return;
    gelegteBreite = bild.clientWidth;
    kachelnSetzen();
  });
  K.bildBeobachter.observe(bild);

  // Beim Verkleinern des Fensters aendert sich der Faktor — sonst laegen die Rahmen
  // nach jedem Ziehen am Fensterrand wieder daneben.
  K.kachelnSetzen = kachelnSetzen;
  K.vorschauAnpassen = vorschauAnpassen;
  /* ⚠⚠ Die Warnung aus dem letzten Umzug hier setzen — und NICHT loeschen.
     Zweimal zu kurz gesprungen: erst direkt gesetzt (die Vorschau 350 ms spaeter
     ueberschrieb sie), dann hier gesetzt und gleich geloescht — `waehle()` loest beim
     Screenwechsel aber eine EIGENE Vorschau aus, die frueher zurueckkommt: die Warnung
     blitzte auf und war weg, bevor jemand sie lesen konnte. Sie bleibt jetzt stehen, bis
     etwas anderes angewaehlt wird (`waehle` raeumt sie weg). */
  hinweisSetzen(K.umzugHinweis);
}

/* Kacheln lassen sich ziehen. Raster-Kacheln rasten in Zellen ein, absolut
   platzierte gehen pixelweise — das entspricht dem, was in der YAML steht, und
   verwandelt eine `cell` nicht heimlich in ein `at`. */
function ziehbarMachen(r, kc) {
  let start = null;

  r.onmousedown = (ev) => {
    if (ev.button !== 0) return;
    ev.preventDefault();
    waehle(kc.pfad);
    start = { x: ev.clientX, y: ev.clientY, bewegt: false };

    const bewegen = (e) => {
      // Derselbe Faktor wie beim Setzen der Rahmen — sonst wandert die Kachel unter
      // dem Mauszeiger weg, sobald der Browser das Bild verkleinert hat.
      const f = K.zoom * K.skala;
      const dx = Math.round((e.clientX - start.x) / f);
      const dy = Math.round((e.clientY - start.y) / f);
      if (!start.bewegt && Math.abs(dx) + Math.abs(dy) < 1) return;
      start.bewegt = true;
      r.style.transform = `translate(${dx * f}px, ${dy * f}px)`;
      hinweisSetzen(versatzText(kc, dx, dy));
    };

    const loslassen = (e) => {
      document.removeEventListener('mousemove', bewegen);
      document.removeEventListener('mouseup', loslassen);
      r.style.transform = '';
      if (!start.bewegt) { start = null; return; }
      const f = K.zoom * K.skala;
      const dx = Math.round((e.clientX - start.x) / f);
      const dy = Math.round((e.clientY - start.y) / f);
      start = null;
      verschiebe(kc, dx, dy);
    };

    document.addEventListener('mousemove', bewegen);
    document.addEventListener('mouseup', loslassen);
  };
}

function raster() {
  const p = (K.daten.panels || [])[panelIndex()] || {};
  const g = p.grid || {};
  return { zeile: g.row_height || 9, spalte: g.col_width || 32 };
}

function versatzText(kc, dx, dy) {
  const g = raster();
  if (kc.raster) {
    const dz = Math.round(dy / g.zeile), ds = Math.round(dx / g.spalte);
    return `Zelle ${dz >= 0 ? '+' : ''}${dz} Zeilen, ${ds >= 0 ? '+' : ''}${ds} Spalten`;
  }
  return `${dx >= 0 ? '+' : ''}${dx}, ${dy >= 0 ? '+' : ''}${dy} px`;
}

function verschiebe(kc, dx, dy) {
  const w = hole(kc.pfad);
  if (!w) return;
  const g = raster();
  if (kc.feld === 'region' && Array.isArray(w.region)) {
    if (!dx && !dy) return;
    w.region = [Math.max(0, w.region[0] + dx), Math.max(0, w.region[1] + dy),
                w.region[2], w.region[3]];
  } else if (kc.raster && Array.isArray(w.cell)) {
    const dz = Math.round(dy / g.zeile), ds = Math.round(dx / g.spalte);
    if (!dz && !ds) return;
    w.cell = [Math.max(0, w.cell[0] + dz), Math.max(0, w.cell[1] + ds)];
  } else if (Array.isArray(w.at)) {
    if (!dx && !dy) return;
    w.at = [Math.max(0, w.at[0] + dx), Math.max(0, w.at[1] + dy)];
    // Ein eigenes Textfeld wandert mit — sonst zerfaellt die Kachel beim Verschieben.
    if (Array.isArray(w.text_at)) {
      w.text_at = [Math.max(0, w.text_at[0] + dx), Math.max(0, w.text_at[1] + dy)];
    }
  } else {
    return;
  }
  K.schmutzig = true;
  kopfAktualisieren();
  formularZeichnen();
  nachAenderung();
}

function hinweisSetzen(text) {
  const h = document.getElementById('k-hinweis');
  if (h) h.textContent = text || T('ui.ziehen_hinweis');
}

function markiereKachel() {
  document.querySelectorAll('.k-kachel').forEach((r, i) => {
    r.classList.toggle('aktiv', gleich(K.kacheln[i] && K.kacheln[i].pfad, K.auswahl));
  });
}

/* --- Formular ----------------------------------------------------------- */
function formularZeichnen() {
  const ziel = document.getElementById('k-form');
  ziel.innerHTML = '';
  if (!K.auswahl) { ziel.append(el('div', 'k-hinweis', T('ui.keine_auswahl'))); return; }

  const pfad = K.auswahl;
  const letzter = pfad[pfad.length - 1];
  const vorletzter = pfad[pfad.length - 2];
  let gruppe = null, titel = '';

  if (gleich(pfad, ['fonts'])) { schriftFormular(ziel); return; }
  if (gleich(pfad, ['defaults'])) { gruppe = 'defaults'; titel = T('ui.vorgaben'); }
  else if (vorletzter === 'widgets') { gruppe = 'widget'; titel = T('ui.widgets'); }
  else if (vorletzter === 'screens') { gruppe = 'screen'; titel = T('ui.screens'); }
  else if (vorletzter === 'seiten') { gruppe = 'seite'; titel = T('ui.seiten'); }
  else if (vorletzter === 'screen_groups') { gruppe = 'screen_group'; titel = T('ui.screen_gruppen'); }
  else if (letzter === 'notify') { gruppe = 'notify'; titel = T('ui.notify'); }
  else if (vorletzter === 'panels') { gruppe = 'panel'; titel = T('ui.anzeige'); }

  if (!gruppe) { ziel.append(el('div', 'k-hinweis', T('ui.keine_auswahl'))); return; }

  const kopf = el('h3', null, titel);
  ziel.append(kopf);
  const form = el('div', 'k-form');
  ziel.append(form);

  const knoten_ = hole(pfad) || {};
  /* ⚠ Felder mit `nur_typ` gehoeren nur zu bestimmten Widget-Typen (`image` zur Bilddatei,
     die Meldungsfelder zu `notify`). Sie ALLEN Typen zu zeigen, hiess frueher: an einer Uhr
     stand ein Feld „Bilddatei", das nichts tut — und mit den Meldungsfeldern waere das
     Formular jeder Kachel um acht wirkungslose Zeilen gewachsen. Gefiltert wird nur die
     ANZEIGE; die Pruefung bleibt eine flache Schluesselmenge, damit ein Typwechsel nicht
     wieder zur Sackgasse wird. */
  const passt = (f) => !f.nur_typ || f.nur_typ.includes(knoten_.type || 'tile');
  K.schema[gruppe].filter(passt).forEach(f => form.append(feldBauen(f, pfad, knoten_)));

  if (gruppe === 'widget') {
    /* Felder eines eigenen Typs aus /config/aton_widgets. Sie stehen im Widget selbst
       (nicht in einem Unterzweig), deshalb reicht derselbe Pfad wie oben. */
    const eigen = (K.schema.widget_eigene || {})[knoten_.type];
    if (eigen && eigen.felder.length) {
      form.append(el('h3', null, eigen.name));
      if (eigen.beschreibung) form.append(el('div', 'k-hilfe', eigen.beschreibung));
      form.append(el('div', 'k-hilfe', eigen.quelle));
      eigen.felder.forEach(f => form.append(feldBauen(f, pfad, knoten_)));
    }
    form.append(el('h3', null, T('ui.beschreibung')));
    K.schema.textquelle.forEach(f => form.append(feldBauen(f, pfad, knoten_)));
  }

  // Unterabschnitte einer Anzeige
  if (gruppe === 'panel') {
    ['gate', 'brightness', 'grid'].forEach(name => {
      form.append(el('h3', null, name));
      const unterpfad = pfad.concat([name]);
      // Der Zweig wird BEWUSST nicht hier angelegt, sondern erst beim Eintragen eines
      // Wertes (`setze` legt fehlende Stufen an). Sonst stuende in der Datei nach jedem
      // Blick ins Formular ein leeres `gate: {}`.
      K.schema[name].forEach(f => form.append(feldBauen(f, unterpfad, hole(unterpfad) || {})));
    });
  }

  form.append(werkzeugZeile(pfad, gruppe));
}

/* Der Abschnitt `fonts:` ist NICHT die Liste der Schriften — die liefert die App. Hier
   stehen nur Regeln je Schrift: Grossschrift und Umlaut-Ersatzschreibung. Beides ist eine
   Eigenschaft der SCHRIFT (in 5 px Hoehe sind Kleinbuchstaben unlesbar und ueber einem
   vollhohen Buchstaben ist kein Platz fuer Umlautpunkte), deshalb steht es nicht im Code.

   Das Formular muss vor allem eines zeigen: ob eine Regel gilt, WEIL sie eingebaut ist,
   oder weil jemand sie eingetragen hat. Sonst dreht man an etwas, das man gar nicht
   gesetzt hat. */
function schriftFormular(ziel) {
  ziel.append(el('h3', null, T('ui.schriften')));
  const form = el('div', 'k-form');
  ziel.append(form);
  form.append(el('div', 'k-hilfe', T('ui.schriften_hilfe')));

  const eintraege = K.daten.fonts || {};
  const namen = Object.keys(eintraege).sort();

  if (!namen.length) form.append(el('div', 'k-hinweis', T('ui.schriften_leer')));

  namen.forEach(name => {
    const kasten = el('div', 'k-schrift');
    const kopf = el('div', 'k-schrift-kopf');
    kopf.append(el('span', 'k-name', name));
    const weg = el('button', 'k-knopf k-gefahr', '\u00d7');
    weg.title = T('ui.loeschen');
    weg.onclick = () => { delete K.daten.fonts[name]; K.schmutzig = true;
                          formularZeichnen(); nachAenderung(); };
    kopf.append(weg);
    kasten.append(kopf);

    if (!K.schriften.includes(name)) {
      kasten.append(el('div', 'k-marke-warn k-hilfe', T('ui.schrift_unbekannt')));
    }
    K.schema.schrift_optionen.forEach(f => {
      const eingebaut = (K.schriftVorgaben[name] || {})[f.name];
      const label = el('label');
      const kb = el('input'); kb.type = 'checkbox';
      const gesetzt = eintraege[name][f.name] !== undefined;
      kb.checked = gesetzt ? !!eintraege[name][f.name] : !!eingebaut;
      kb.onchange = () => { K.daten.fonts[name][f.name] = kb.checked;
                            K.schmutzig = true; formularZeichnen(); nachAenderung(); };
      const zeile = el('span');
      zeile.append(kb, document.createTextNode(' ' + f.label));
      label.append(zeile);
      if (!gesetzt && eingebaut !== undefined) {
        label.append(el('div', 'k-hilfe', T('ui.eingebaut')));
      }
      label.append(el('div', 'k-hilfe', f.hilfe));
      kasten.append(label);
    });
    form.append(kasten);
  });

  // Eintrag anlegen: aus der Liste der bekannten Schriften waehlen, eigene Namen
  // (etwa `arial@8`) sind aber ebenso erlaubt — daher ein Textfeld mit Liste.
  const neu = el('div', 'k-zeile');
  const feld = el('input'); feld.type = 'text';
  feld.setAttribute('list', 'k-schriftliste');
  feld.placeholder = T('ui.schrift_waehlen');
  const liste = el('datalist'); liste.id = 'k-schriftliste';
  K.schriften.filter(n => !(n in eintraege)).forEach(n => liste.append(new Option(n, n)));
  const knopf = el('button', 'k-knopf', '+ ' + T('ui.hinzufuegen'));
  knopf.onclick = () => {
    const name = feld.value.trim();
    if (!name || (K.daten.fonts || {})[name]) return;
    if (!K.daten.fonts) K.daten.fonts = {};
    const v = K.schriftVorgaben[name] || {};
    K.daten.fonts[name] = { uppercase: !!v.uppercase, transliterate: !!v.transliterate };
    K.schmutzig = true;
    formularZeichnen(); nachAenderung();
  };
  neu.append(feld, liste, knopf);
  form.append(neu);
}

/* Beim Wechsel des Typs die Schluessel des ALTEN eigenen Typs mitnehmen.

   ⚠⚠ Sonst bleibt `sensor: …` von einem `bargraph` stehen, und der naechste Typ lehnt die
   ganze Beschreibung ab: „unbekannte Schluessel: sensor". Die Meldung stimmt und hilft
   trotzdem nicht — man hat den Schluessel nie von Hand hingeschrieben und kann ihn im
   Formular auch nicht mehr sehen, weil das Feld mit dem alten Typ verschwunden ist. Ohne
   dieses Aufraeumen ist der Typwechsel eine Sackgasse, aus der nur der YAML-Editor
   herausfuehrt.

   Schluessel, die der NEUE Typ ebenfalls kennt, bleiben stehen — zwei Plugins duerfen
   sich ein `sensor` teilen, ohne dass der Wechsel ihn wegwirft. */
function typwechselAufraeumen(knoten_, alterTyp, neuerTyp) {
  const eigene = K.schema.widget_eigene || {};
  const alt = eigene[alterTyp];
  if (!alt || alterTyp === neuerTyp) return;
  const neu = eigene[neuerTyp];
  const behalten = new Set((neu ? neu.felder : []).map(x => x.name));
  alt.felder.forEach(x => { if (!behalten.has(x.name)) delete knoten_[x.name]; });
}

function feldBauen(f, pfad, knoten_) {
  const label = el('label');
  label.append(el('span', 'k-label', f.label + (f.pflicht ? ' *' : '')));
  const wert = knoten_ ? knoten_[f.name] : undefined;
  const feldpfad = pfad.concat([f.name]);
  let eingabe;

  switch (f.art) {
    case 'bool': {
      eingabe = el('select');
      [['', '—'], ['true', 'ja / yes'], ['false', 'nein / no']].forEach(([v, t]) =>
        eingabe.add(new Option(t, v)));
      eingabe.value = wert === undefined ? '' : String(!!wert);
      eingabe.onchange = () => setze(feldpfad,
        eingabe.value === '' ? undefined : eingabe.value === 'true');
      break;
    }
    case 'auswahl': {
      eingabe = el('select');
      eingabe.add(new Option('—', ''));
      (f.optionen || []).forEach(o => eingabe.add(new Option(o, o)));
      eingabe.value = wert === undefined ? '' : wert;
      eingabe.onchange = () => {
        if (f.name === 'type') typwechselAufraeumen(knoten_, wert, eingabe.value);
        setze(feldpfad, eingabe.value || undefined);
        /* Der Typ entscheidet, WELCHE Felder darunter stehen — eigene Typen bringen ihre
           eigenen mit. Ohne das Neuzeichnen bliebe das Formular auf dem alten Typ stehen
           und man haette die Felder erst nach einem Klick anderswohin und zurueck. */
        if (f.name === 'type') formularZeichnen();
        nachAenderung();
      };
      break;
    }
    case 'schrift': {
      eingabe = el('select');
      eingabe.add(new Option('—', ''));
      K.schriften.forEach(s => eingabe.add(new Option(s, s)));
      eingabe.value = wert === undefined ? '' : wert;
      eingabe.onchange = () => { setze(feldpfad, eingabe.value || undefined); nachAenderung(); };
      break;
    }
    case 'int': case 'float': {
      eingabe = el('input'); eingabe.type = 'number';
      if (f.art === 'float') eingabe.step = 'any';
      if (f.min !== undefined) eingabe.min = f.min;
      if (f.max !== undefined) eingabe.max = f.max;
      eingabe.value = wert === undefined ? '' : wert;
      eingabe.onchange = () => {
        setze(feldpfad, eingabe.value === '' ? undefined :
          (f.art === 'int' ? parseInt(eingabe.value, 10) : parseFloat(eingabe.value)));
        nachAenderung();
      };
      break;
    }
    case 'farbe': {
      /* ⚠ Ein <input type=color> hat keinen leeren Zustand — er zeigt IMMER eine Farbe.
         Frueher stand da fest '#ffffff', und ein nicht gesetzter Hintergrund sah aus wie
         ein weisser. Jetzt zeigt das Feld die tatsaechlich wirkende Vorgabe (aus dem
         Schema, sonst Schwarz) und ist ausgegraut, solange nichts gesetzt ist. */
      eingabe = el('div', 'k-farbe');
      const gesetzt = typeof wert === 'string' && wert !== '';
      const t = el('input'); t.type = 'text'; t.value = gesetzt ? wert : '';
      t.placeholder = f.vorgabe ? f.vorgabe : T('ui.nicht_gesetzt');
      const c = el('input'); c.type = 'color';
      const ersatz = (typeof f.vorgabe === 'string' ? f.vorgabe : '000000').replace('#', '');
      c.value = '#' + (gesetzt ? wert.replace('#', '') : ersatz);
      c.classList.toggle('k-ungesetzt', !gesetzt);
      c.title = gesetzt ? wert : T('ui.nicht_gesetzt');

      const uebernimm = (v) => {
        setze(feldpfad, v || undefined);
        t.value = v || '';
        c.classList.toggle('k-ungesetzt', !v);
        c.title = v || T('ui.nicht_gesetzt');
        nachAenderung();
      };
      t.onchange = () => uebernimm(t.value.replace('#', '').trim());
      c.oninput = () => uebernimm(c.value.slice(1));

      eingabe.append(t, c);
      if (!f.pflicht) {
        const leeren = el('button', 'k-knopf', '\u00d7');
        leeren.title = T('ui.zuruecksetzen');
        leeren.onclick = (ev) => { ev.preventDefault(); c.value = '#' + ersatz; uebernimm(''); };
        eingabe.append(leeren);
      }
      break;
    }
    case 'zelle': case 'punkt': case 'groesse': {
      eingabe = el('div', 'k-paar');
      const a = el('input'); a.type = 'number';
      const b = el('input'); b.type = 'number';
      a.placeholder = f.art === 'zelle' ? 'Zeile' : (f.art === 'groesse' ? 'B' : 'x');
      b.placeholder = f.art === 'zelle' ? 'Spalte' : (f.art === 'groesse' ? 'H' : 'y');
      if (Array.isArray(wert)) { a.value = wert[0]; b.value = wert[1]; }
      const schreib = () => {
        if (a.value === '' && b.value === '') setze(feldpfad, undefined);
        else setze(feldpfad, [parseInt(a.value || 0, 10), parseInt(b.value || 0, 10)]);
        nachAenderung();
      };
      a.onchange = schreib; b.onchange = schreib;
      eingabe.append(a, b);
      break;
    }
    case 'rechteck': {
      eingabe = el('div', 'k-paar');
      const felder = ['x', 'y', 'B', 'H'].map((ph, i) => {
        const n = el('input'); n.type = 'number'; n.placeholder = ph;
        if (Array.isArray(wert)) n.value = wert[i];
        return n;
      });
      const schreib = () => {
        if (felder.every(n => n.value === '')) setze(feldpfad, undefined);
        else setze(feldpfad, felder.map(n => parseInt(n.value || 0, 10)));
        nachAenderung();
      };
      felder.forEach(n => { n.onchange = schreib; eingabe.append(n); });
      break;
    }
    case 'vorlage': {
      eingabe = el('textarea');
      eingabe.value = wert === undefined ? '' : wert;
      eingabe.onchange = () => { setze(feldpfad, eingabe.value || undefined); nachAenderung(); };
      break;
    }
    case 'entitaet': {
      eingabe = entitaetsFeld(wert, (v) => { setze(feldpfad, v || undefined); nachAenderung(); });
      break;
    }
    case 'symbolquelle': case 'farbquelle': {
      eingabe = quellenFeld(f, feldpfad, wert);
      break;
    }
    case 'symbol': {
      eingabe = symbolFeld(wert, (v) => { setze(feldpfad, v || undefined); nachAenderung(); });
      break;
    }
    default: {
      eingabe = el('input'); eingabe.type = 'text';
      eingabe.value = wert === undefined ? '' : wert;
      eingabe.onchange = () => { setze(feldpfad, eingabe.value || undefined); nachAenderung(); };
    }
  }

  label.append(eingabe);
  if (f.hilfe) label.append(el('div', 'k-hilfe', f.hilfe));
  return label;
}

/* Entitaets-Auswahl mit Suche aus dem Zustandsspiegel der App. */
function entitaetsFeld(wert, beiWahl) {
  const huelle = el('div');
  huelle.style.position = 'relative';
  const e = el('input'); e.type = 'text'; e.value = wert || '';
  e.placeholder = 'sensor.…';
  huelle.append(e);
  let liste = null;
  const schliessen = () => { if (liste) { liste.remove(); liste = null; } };

  e.oninput = async () => {
    schliessen();
    const q = e.value.trim();
    if (q.length < 2) return;
    const d = await (await fetch('api/entities?limit=25&q=' + encodeURIComponent(q))).json();
    liste = el('div', 'k-vorschlag');
    d.entitaeten.forEach(x => {
      const z = el('div', x.leer ? 'k-leer' : null, `${x.id}  ·  ${x.zustand}`);
      z.onclick = () => { e.value = x.id; beiWahl(x.id); schliessen(); };
      liste.append(z);
    });
    huelle.append(liste);
  };
  e.onchange = () => beiWahl(e.value.trim());
  e.onblur = () => setTimeout(schliessen, 180);
  return huelle;
}

function symbolFeld(wert, beiWahl) {
  const huelle = el('div');
  const gitter = el('div', 'k-symbolgitter');
  /* ⚠ Erste Kachel: KEIN Symbol. Ohne sie kommt man an ein einmal gesetztes `icon:` nie
     wieder heran — jeder Klick ins Gitter SETZT einen Namen, ein leerer Zustand war gar
     nicht waehlbar. Getroffen hat es vor allem Typen, die ueberhaupt kein Symbol zeichnen
     (`clock_wd`, `calendar`): dort blieb ein Symbol des vorherigen Typs als Ballast in der
     Datei stehen und wurde im Baum als Name der Kachel angezeigt. */
  const leer = el('div', 'k-leer' + (wert ? '' : ' aktiv'), '—');
  leer.title = T('ui.kein_symbol');
  leer.onclick = () => { beiWahl(undefined); formularZeichnen(); };
  gitter.append(leer);
  K.symbole.forEach(name => {
    const b = el('img');
    b.src = 'api/icons/' + encodeURIComponent(name) + `.png?zoom=5&t=${K.symbolMarke || 0}`;
    b.title = name;
    if (name === wert) b.className = 'aktiv';
    b.onclick = () => { beiWahl(name); formularZeichnen(); };
    gitter.append(b);
  });
  huelle.append(gitter);
  return huelle;
}

/* Symbol und Farbe koennen fest sein oder aus dem Zustand kommen — vier Formen. */
function quellenFeld(f, feldpfad, wert) {
  const huelle = el('div');
  const form = el('select');
  // ⚠ Nur die Beschriftung wird uebersetzt — der WERT bleibt englisch/technisch,
  // er entscheidet ueber die Form, die in die Beschreibung geschrieben wird.
  [['name', T('ui.fest')], ['map', 'map'], ['steps', 'steps'], ['template', T('ui.vorlage')]]
    .forEach(([v, t]) => form.add(new Option(t, v)));
  const istObjekt = wert && typeof wert === 'object';
  const aktuelleForm = !istObjekt ? 'name'
    : (wert.template ? 'template' : (wert.steps ? 'steps' : (wert.map ? 'map' : 'name')));
  form.value = aktuelleForm;
  huelle.append(form);

  const koerper = el('div');
  koerper.style.marginTop = '6px';
  huelle.append(koerper);

  /* ⚠ Den Wert bei JEDEM Zeichnen frisch aus den Daten holen. `wert` stammt aus dem Aufbau
     des Formulars, und ein Formwechsel loescht den Eintrag (`form.onchange` unten) — danach
     zeigte das Gitter weiter ein Symbol als aktiv, das in der Datei gar nicht mehr stand. */
  const jetzt = () => {
    const w = hole(feldpfad);
    return [w, w && typeof w === 'object'];
  };

  const zeichne = () => {
    koerper.innerHTML = '';
    const [w, objekt] = jetzt();
    const art = form.value;
    if (art === 'name') {
      if (f.art === 'symbolquelle') {
        koerper.append(symbolFeld(typeof w === 'string' ? w : (objekt ? w.name : ''),
          v => { setze(feldpfad, v); nachAenderung(); }));
      } else {
        const t = el('input'); t.type = 'text';
        t.value = typeof w === 'string' ? w : '';
        t.placeholder = 'rrggbb';
        t.onchange = () => { setze(feldpfad, t.value || undefined); nachAenderung(); };
        koerper.append(t);
      }
      return;
    }
    if (art === 'template') {
      const t = el('textarea');
      t.value = objekt ? (w.template || '') : '';
      t.onchange = () => { setze(feldpfad, { template: t.value }); nachAenderung(); };
      koerper.append(t);
      return;
    }
    // map / steps: Entitaet + Zeilenpaare
    const ent = entitaetsFeld(objekt ? w.value : '', v => {
      const [a, aObjekt] = jetzt();
      const neu = Object.assign({}, aObjekt ? a : {}, { value: v });
      setze(feldpfad, neu); nachAenderung();
    });
    koerper.append(ent);
    const tabelle = el('div');
    const eintraege = Object.entries((objekt && w[art]) || {});
    const schreib = () => {
      const obj = {};
      tabelle.querySelectorAll('.k-paar').forEach(z => {
        const [k, v] = z.querySelectorAll('input');
        if (k.value !== '') obj[k.value] = v.value;
      });
      const [a, aObjekt] = jetzt();
      const neu = Object.assign({}, aObjekt ? a : {});
      neu[art] = obj;
      setze(feldpfad, neu); nachAenderung();
    };
    const zeile = (k, v) => {
      const z = el('div', 'k-paar');
      z.style.marginTop = '4px';
      const a = el('input'); a.type = 'text'; a.value = k;
      a.placeholder = art === 'steps' ? '≥ Schwelle' : 'Zustand';
      const b = el('input'); b.type = 'text'; b.value = v; b.placeholder = 'Symbol/Farbe';
      const weg = el('button', 'k-knopf k-gefahr', '×');
      weg.onclick = () => { z.remove(); schreib(); };
      a.onchange = schreib; b.onchange = schreib;
      z.append(a, b, weg);
      return z;
    };
    eintraege.forEach(([k, v]) => tabelle.append(zeile(k, String(v))));
    koerper.append(tabelle);
    const plus = el('button', 'k-knopf', '+ ' + T('ui.hinzufuegen'));
    plus.onclick = () => tabelle.append(zeile('', ''));
    koerper.append(plus);
  };
  form.onchange = () => { setze(feldpfad, undefined); zeichne(); };
  zeichne();
  return huelle;
}

/* --- Werkzeuge am Knoten ------------------------------------------------ */
/* Alle Listen, in die eine Kachel umziehen kann: das Grundbild jeder Anzeige und jede
   Seite jedes Screens. Beschriftet mit dem ganzen Weg, damit bei gleichnamigen Screens in
   zwei Anzeigen klar ist, welcher gemeint ist. */
function kachelZiele() {
  const ziele = [];
  (K.daten.panels || []).forEach((p, pi) => {
    const anzeige = p.name || p.id || `#${pi}`;
    ziele.push({ pfad: ['panels', pi, 'widgets'], text: `${anzeige} › ${T('ui.grundbild')}` });
    (p.screen_groups || []).forEach((g, gi) => {
      const gname = g.name || g.id || `#${gi}`;
      (g.screens || []).forEach((sc, si) => {
        const basis = ['panels', pi, 'screen_groups', gi, 'screens', si];
        if (Array.isArray(sc.seiten) && sc.seiten.length) {
          sc.seiten.forEach((se, sj) => ziele.push({
            pfad: basis.concat(['seiten', sj, 'widgets']),
            text: `${anzeige} › ${gname} › ${sc.name || si} › ${se.name || `${T('ui.seiten')} ${sj + 1}`}`,
          }));
        } else {
          ziele.push({ pfad: basis.concat(['widgets']),
                       text: `${anzeige} › ${gname} › ${sc.name || si}` });
        }
      });
    });
  });
  return ziele;
}

/* Passt die Kachel dort ueberhaupt hin? Verschoben wird trotzdem — aber gesagt wird es.

   ⚠ Zwei verschiedene Fragen: die Flaeche der ANZEIGE (harte Grenze, was darueber hinaus
   liegt, zeichnet nie) und der Bereich der SCREEN-GRUPPE (weiche Grenze: gezeichnet wird
   es, aber die Gruppe tauscht nur ihren `region`-Ausschnitt aus — eine Kachel ausserhalb
   bliebe beim Screenwechsel stehen). */
function kachelPasstNicht(kachel, zielPfad) {
  const pi = zielPfad[1];
  const panel = (K.daten.panels || [])[pi];
  if (!panel || !Array.isArray(panel.size)) return '';
  const g = panel.grid || {};
  const spalte = g.col_width || 32, zeile = g.row_height || 9;
  let x, y;
  if (Array.isArray(kachel.cell)) { y = kachel.cell[0] * zeile; x = kachel.cell[1] * spalte; }
  else if (Array.isArray(kachel.at)) { [x, y] = kachel.at; }
  else return '';
  const [b, h] = Array.isArray(kachel.size) ? kachel.size : [spalte, 8];
  const [pb, ph] = panel.size;

  if (x < 0 || y < 0 || x + b > pb || y + h > ph) {
    return T('ui.ausserhalb_flaeche').replace('%s', `${pb}×${ph}`);
  }
  if (zielPfad[2] === 'screen_groups') {
    const r = ((panel.screen_groups || [])[zielPfad[3]] || {}).region;
    if (Array.isArray(r) && (x < r[0] || y < r[1] || x + b > r[0] + r[2] || y + h > r[1] + r[3])) {
      return T('ui.ausserhalb_bereich').replace('%s', r.join(', '));
    }
  }
  return '';
}

function kachelVerschieben(vonPfad, zielPfad) {
  const quelle = hole(vonPfad.slice(0, -1));
  const index = vonPfad[vonPfad.length - 1];
  if (!Array.isArray(quelle)) return;
  // ⚠ Die Zielliste kann fehlen (Screen ohne `widgets:`) — `setze` legt fehlende Stufen an.
  if (!Array.isArray(hole(zielPfad))) setze(zielPfad, []);
  const ziel = hole(zielPfad);

  const kachel = quelle.splice(index, 1)[0];
  ziel.push(kachel);
  K.schmutzig = true;

  const warnung = kachelPasstNicht(kachel, zielPfad);
  const neuerPfad = zielPfad.concat([ziel.length - 1]);
  waehle(neuerPfad);
  zeichneAlles();
  /* ⚠ Den Hinweis NICHT direkt setzen: `nachAenderung` holt 350 ms spaeter die Vorschau,
     und die setzt die Hinweiszeile auf ihren Standardtext zurueck — die Warnung war nach
     einem Wimpernschlag wieder weg (beim Testen genau so erlebt). Sie reist deshalb als
     `K.umzugHinweis` mit und wird von `vorschauHolen` gesetzt, wenn das neue Bild steht. */
  K.umzugHinweis = warnung;
  nachAenderung();
}

function werkzeugZeile(pfad, gruppe) {
  const z = el('div', 'k-zeile');
  const vorletzter = pfad[pfad.length - 2];
  const index = pfad[pfad.length - 1];

  if (typeof index === 'number') {
    const liste = hole(pfad.slice(0, -1));
    const rauf = el('button', 'k-knopf', '↑');
    rauf.title = T('ui.nach_oben');
    rauf.disabled = index === 0;
    rauf.onclick = () => { liste.splice(index - 1, 0, liste.splice(index, 1)[0]);
                           K.schmutzig = true; waehle(pfad.slice(0, -1).concat([index - 1]));
                           nachAenderung(); };
    const runter = el('button', 'k-knopf', '↓');
    runter.title = T('ui.nach_unten');
    runter.disabled = index >= liste.length - 1;
    runter.onclick = () => { liste.splice(index + 1, 0, liste.splice(index, 1)[0]);
                             K.schmutzig = true; waehle(pfad.slice(0, -1).concat([index + 1]));
                             nachAenderung(); };
    const kopie = el('button', 'k-knopf', T('ui.duplizieren'));
    kopie.onclick = () => { liste.splice(index + 1, 0, JSON.parse(JSON.stringify(liste[index])));
                            K.schmutzig = true; waehle(pfad.slice(0, -1).concat([index + 1]));
                            nachAenderung(); };
    const weg = el('button', 'k-knopf k-gefahr', T('ui.loeschen'));
    weg.onclick = () => { liste.splice(index, 1); K.schmutzig = true;
                          K.auswahl = null; zeichneAlles(); nachAenderung(); };
    z.append(rauf, runter, kopie, weg);
  }

  /* Umzug in eine andere Liste — ↑/↓ kommen nur INNERHALB einer Liste voran. Damit geht
     „aus dem Grundbild in eine Screen-Gruppe" und auch der Wechsel zwischen zwei Anzeigen.
     ⚠ Koordinaten bleiben unveraendert; ob die Kachel im Ziel noch im Bild liegt, prueft
     `kachelPasstNicht` und sagt es in der Hinweiszeile. Umgerechnet wird BEWUSST nicht:
     eine Kachel, die woanders landet als dort, wo man sie hingeschoben hat, ueberrascht. */
  if (vorletzter === 'widgets' && typeof index === 'number') {
    const eigenerPfad = schluessel(pfad.slice(0, -1));
    const ziele = kachelZiele().filter(zi => schluessel(zi.pfad) !== eigenerPfad);
    if (ziele.length) {
      const zeile = el('div', 'k-zeile');
      zeile.style.marginTop = '6px';
      const wahl = el('select');
      wahl.add(new Option(T('ui.verschieben_nach'), ''));
      ziele.forEach(zi => wahl.add(new Option(zi.text, schluessel(zi.pfad))));
      wahl.onchange = () => {
        const treffer = ziele.find(zi => schluessel(zi.pfad) === wahl.value);
        if (treffer) kachelVerschieben(pfad, treffer.pfad);
      };
      zeile.append(wahl);
      z.append(zeile);
    }
  }

  // Wo man gerade steht, entscheidet, WOHIN eine neue Kachel gehoert.
  const kachelziel = vorletzter === 'widgets' ? pfad.slice(0, -1)
                   : (gruppe === 'screen' || gruppe === 'panel') ? pfad.concat(['widgets'])
                   : null;
  if (kachelziel) {
    const neu = el('button', 'k-knopf', '+ ' + T('ui.kachel'));
    neu.onclick = () => anlegen(kachelziel);
    z.append(neu);
  }
  if (gruppe === 'screen_group') {
    const neu = el('button', 'k-knopf', '+ ' + T('ui.screens'));
    neu.onclick = () => anlegen(pfad.concat(['screens']));
    z.append(neu);
  }
  if (gruppe === 'panel') {
    const neu = el('button', 'k-knopf', '+ ' + T('ui.screen_gruppen'));
    neu.onclick = () => anlegen(pfad.concat(['screen_groups']));
    z.append(neu);
  }
  // Eine weitere Anzeige anlegen. Auch unter „Vorgaben" erreichbar — sonst kaeme man an
  // den Knopf nicht heran, solange noch gar keine Anzeige da ist.
  if (gruppe === 'panel' || gruppe === 'defaults') {
    const neu = el('button', 'k-knopf', '+ ' + T('ui.anzeige'));
    neu.onclick = () => anlegen(['panels']);
    z.append(neu);
  }
  if (gruppe === 'notify' && hole(pfad)) {
    const um = el('button', 'k-knopf', T('ui.in_kachel_umwandeln'));
    um.title = T('ui.in_kachel_umwandeln_hilfe');
    um.onclick = () => notifyZuKachel(pfad);
    z.append(um);
  }
  return z;
}

/* Den alten Block `notify:` in eine Kachel `type: notify` umschreiben.

   Die App versteht beide Schreibweisen — der Block wird beim Laden ohnehin uebersetzt.
   Was er NICHT kann: sich in der Vorschau anfassen lassen. Seine Lage steht als `region:`
   in Zahlen da, waehrend jede Kachel mit der Maus liegt, wo sie liegen soll. Genau deshalb
   dieser Knopf — ein Weg von der alten in die neue Schreibweise, ohne YAML-Editor. */
function notifyZuKachel(pfad) {
  const block = hole(pfad);
  if (!block || !Array.isArray(block.region)) return;
  const [x, y, breite, hoehe] = block.region;
  const kachel = { type: 'notify', at: [x, y], size: [breite, hoehe] };
  // ⚠ `layer: 1` MUSS mit: der Block lag im Renderer immer ueber den Screen-Gruppen, eine
  // Kachel auf Ebene 0 laege darunter. Ohne diese Zeile waere die Meldung nach dem
  // Umwandeln je nach Aufbau schlicht verdeckt — und das saehe aus wie „kommt nicht an".
  kachel.layer = 1;
  Object.keys(block).forEach(k => { if (k !== 'region') kachel[k] = block[k]; });

  const panelpfad = pfad.slice(0, -1);
  const panel = hole(panelpfad);
  if (!Array.isArray(panel.widgets)) panel.widgets = [];
  panel.widgets.push(kachel);
  delete panel.notify;
  K.schmutzig = true;
  waehle(panelpfad.concat(['widgets', panel.widgets.length - 1]));
  zeichneAlles();
  nachAenderung();
}

let warten = null;
function nachAenderung() {
  baumZeichnen();
  clearTimeout(warten);
  warten = setTimeout(vorschauHolen, 350);   // nicht bei jedem Tastendruck rendern
}

/* --- Pruefen und Speichern ---------------------------------------------- */
async function pruefenLassen() {
  const m = document.getElementById('k-meldung');
  const a = await (await fetch('api/config/validate', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ daten: K.daten }),
  })).json();
  m.style.display = '';
  m.className = 'k-meldung ' + (a.ok ? 'k-gut' : 'k-fehler');
  m.textContent = a.ok ? '✓' : a.meldung;
  return a.ok;
}

async function speichernLassen() {
  if (!await pruefenLassen()) return;
  const m = document.getElementById('k-meldung');
  const antwort = await fetch('api/config', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ daten: K.daten, mtime: K.mtime }),
  });
  const a = await antwort.json();
  if (!a.ok) {
    m.className = 'k-meldung k-fehler';
    m.textContent = (antwort.status === 409 ? T('ui.datei_extern_geaendert') + '\n' : '')
                  + (a.meldung || T('ui.speichern_fehlgeschlagen'));
    return;
  }
  K.mtime = a.mtime; K.schmutzig = false;
  m.className = 'k-meldung k-gut';
  m.textContent = `${T('ui.gespeichert')} · ${T('ui.gesichert_als')} ${a.sicherung}`;
  if (a.umbenannt && a.umbenannt.length) {
    m.textContent += ` · ${T('ui.namen_umgeschrieben')} `
                   + a.umbenannt.slice(0, 5).join(' · ')
                   + (a.umbenannt.length > 5 ? ` (+${a.umbenannt.length - 5})` : '');
  }
  kopfAktualisieren();
}

function statischeTexte() {
  const setzeText = (id, schluessel) => {
    const e = document.getElementById(id);
    if (e) e.textContent = T(schluessel);
  };
  // Der Stand gehoert neben den Titel und nicht in die Konfigurationsseite: er sagt,
  // welche Fassung der Browser hat — das gilt fuer JEDEN Reiter, auch fuer den, auf dem
  // man gerade steht, wenn etwas nicht so aussieht wie erwartet.
  const stand = document.getElementById('stand');
  if (stand) { stand.textContent = K.stand || ''; stand.title = T('ui.stand'); }
  setzeText('tab-konfig', 'ui.konfiguration');
  setzeText('t-struktur', 'ui.struktur');
  setzeText('t-vorschau', 'ui.vorschau');
  const h = document.getElementById('k-hinweis');
  if (h) h.textContent = T('ui.keine_auswahl');

  // Alles mit `data-i18n` mitnehmen — so braucht eine neue Beschriftung in index.html
  // nur das Attribut und keine Zeile hier. Der deutsche Text bleibt im Markup stehen:
  // er ist der Rueckfall, wenn ein Schluessel fehlt, und macht die Datei fuer sich lesbar.
  document.querySelectorAll('[data-i18n]').forEach(e => {
    e.textContent = T(e.dataset.i18n);
  });

  // ★ Der Betriebs-Reiter wird von index.html gezeichnet, bezieht seine Beschriftungen
  // aber aus derselben Quelle. Er wartet mit dem ERSTEN Zeichnen auf die Texte (sonst
  // blitzen Schluesselnamen auf) — hier ist der Moment, ihn anzustossen. Beim Wechsel
  // der Sprache zeichnet er damit ebenfalls neu.
  if (typeof betriebNeuZeichnen === 'function') betriebNeuZeichnen();
}

document.addEventListener('DOMContentLoaded', () => laden());
// Der Verkleinerungsfaktor haengt an der Spaltenbreite; die aendert sich beim Ziehen
// am Fensterrand. Ohne das lagen die Rahmen danach neben ihren Kacheln.
window.addEventListener('resize', vorschauAnpassen);
window.addEventListener('beforeunload', (e) => { if (K.schmutzig) e.preventDefault(); });
