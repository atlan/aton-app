/* Symbol-Editor — Pixel malen, als PNG mit Alphakanal speichern.

   Warum ein eigener Editor und nicht „mal ein PNG woanders": ein 8x8-Symbol zeichnet man
   nicht in einem Bildprogramm, man pult dort einzelne Pixel. Und der Weg über Datei
   ablegen, Ordner anlegen, neu laden ist drei Schritte zu lang für eine Änderung, die man
   an der Matrix ohnehin gleich sehen will.

   ⚠ Der Alphakanal ist hier keine Zierde. Bei den mitgelieferten Symbolen ist Schwarz
   durchsichtig — wer eine schwarze Fläche will, KANN sie dort nicht malen. Eine eigene
   Datei mit echtem Alpha kann es. Deshalb hat der Editor eine Radiergummi-Stufe (Alpha 0)
   getrennt von der Farbe Schwarz.
*/

const S = {
  breite: 8, hoehe: 8,
  punkte: [],            // 'rrggbbaa' je Pixel, Zeile für Zeile
  farbe: 'ffffff',
  alpha: 255,
  werkzeug: 'stift',     // stift | radierer | pipette
  name: '',
  offen: null,           // welches Symbol geladen wurde (für „Löschen")
  eigen: false,
  zoom: 26,
  schmutzig: false,
  rueckgaengig: [],
};

const SE = (tag, klasse, text) => {
  const e = document.createElement(tag);
  if (klasse) e.className = klasse;
  if (text !== undefined) e.textContent = text;
  return e;
};

/* Eine kleine, für LED-Matrizen brauchbare Palette: satte Grundfarben, keine Pastelltöne.
   Auf einer Matrix mit wenigen Pixeln zählt Kontrast, nicht Nuance. */
const PALETTE = [
  'ffffff', 'c0c0c0', '808080', '404040', '000000',
  'ff0000', 'ff4000', 'ff8000', 'ffc000', 'ffff00',
  '80ff00', '00ff00', '00ff80', '00ffff', '0080ff',
  '0000ff', '8000ff', 'ff00ff', 'ff0080', '804000',
];

function leer(b, h) { return new Array(b * h).fill('00000000'); }

function symbolEditorZeichnen() {
  const ziel = document.getElementById('s-flaeche');
  if (!ziel) return;
  ziel.innerHTML = '';
  if (!S.punkte.length) S.punkte = leer(S.breite, S.hoehe);

  ziel.append(werkzeugleiste());

  const raster = SE('div', 's-raster');
  raster.style.gridTemplateColumns = `repeat(${S.breite}, ${S.zoom}px)`;
  raster.style.width = (S.breite * S.zoom) + 'px';

  let malt = false;
  const setzen = (i) => {
    if (S.werkzeug === 'pipette') {
      const p = S.punkte[i];
      S.farbe = p.slice(0, 6);
      S.alpha = parseInt(p.slice(6, 8), 16);
      S.werkzeug = 'stift';
      symbolEditorZeichnen();
      return;
    }
    const neu = S.werkzeug === 'radierer' ? '00000000'
              : S.farbe + S.alpha.toString(16).padStart(2, '0');
    if (S.punkte[i] === neu) return;
    S.punkte[i] = neu;
    S.schmutzig = true;
    zelleMalen(raster.children[i], neu);
    vorschauAktualisieren();
    kopfSymbol();
  };

  /* ⚠ Der Horcher aufs Loslassen gehoert an den DRUCK, nicht an den Aufbau des Rasters.
     Vorher stand hier ein `document.addEventListener('mouseup', …, {once: true})` beim
     Zeichnen des Feldes: der feuerte einmal und war dann weg. Ab dem ZWEITEN Klick blieb
     `malt` haengen, und das Feld malte beim blossen Darueberfahren weiter. */
  const loslassen = () => { malt = false; };
  for (let i = 0; i < S.breite * S.hoehe; i++) {
    const z = SE('div', 's-zelle');
    z.style.height = S.zoom + 'px';
    zelleMalen(z, S.punkte[i]);
    z.onmousedown = (ev) => {
      ev.preventDefault();
      merken();
      malt = true;
      document.addEventListener('mouseup', loslassen, { once: true });
      setzen(i);
    };
    z.onmouseenter = () => { if (malt) setzen(i); };
    raster.append(z);
  }
  // Verlaesst der Zeiger das Fenster mit gedrueckter Taste, kommt das `mouseup` nie an.
  raster.onmouseleave = () => { if (malt && !document.hasFocus()) malt = false; };

  const mitte = SE('div', 's-mitte');
  mitte.append(raster, vorschauKasten());
  ziel.append(mitte);
  ziel.append(farbwahl());
  ziel.append(fusszeile());
}

/* Durchsichtige Pixel bekommen ein Schachbrett — sonst sieht Alpha 0 aus wie Schwarz,
   und genau die zwei will man ja unterscheiden können. */
function zelleMalen(z, p) {
  const a = parseInt(p.slice(6, 8), 16);
  if (!a) {
    z.style.background = '';
    z.classList.add('s-leer');
  } else {
    z.classList.remove('s-leer');
    z.style.background = `rgba(${parseInt(p.slice(0,2),16)},${parseInt(p.slice(2,4),16)},` +
                         `${parseInt(p.slice(4,6),16)},${a / 255})`;
  }
}

function merken() {
  S.rueckgaengig.push(S.punkte.slice());
  if (S.rueckgaengig.length > 40) S.rueckgaengig.shift();
}

function werkzeugleiste() {
  const z = SE('div', 'k-zeile');
  [['stift', 'ui.stift'], ['radierer', 'ui.radierer'], ['pipette', 'ui.pipette']]
    .forEach(([w, t]) => {
      const b = SE('button', 'k-knopf' + (S.werkzeug === w ? ' k-haupt' : ''), T(t));
      b.onclick = () => { S.werkzeug = w; symbolEditorZeichnen(); };
      z.append(b);
    });

  const fuellen = SE('button', 'k-knopf', T('ui.alles_fuellen'));
  fuellen.onclick = () => {
    merken();
    S.punkte = S.punkte.map(() => S.farbe + S.alpha.toString(16).padStart(2, '0'));
    S.schmutzig = true; symbolEditorZeichnen();
  };
  const leeren = SE('button', 'k-knopf', T('ui.alles_leeren'));
  leeren.onclick = () => {
    merken(); S.punkte = leer(S.breite, S.hoehe);
    S.schmutzig = true; symbolEditorZeichnen();
  };
  const zurueck = SE('button', 'k-knopf', '↶');
  zurueck.title = T('ui.rueckgaengig');
  zurueck.disabled = !S.rueckgaengig.length;
  zurueck.onclick = () => {
    S.punkte = S.rueckgaengig.pop(); S.schmutzig = true; symbolEditorZeichnen();
  };
  z.append(fuellen, leeren, zurueck);
  return z;
}

function farbwahl() {
  const kasten = SE('div', 's-farbwahl');

  const gitter = SE('div', 's-palette');
  PALETTE.forEach(f => {
    const b = SE('div', 's-farbe' + (f === S.farbe ? ' aktiv' : ''));
    b.style.background = '#' + f;
    b.title = '#' + f;
    b.onclick = () => { S.farbe = f; S.werkzeug = 'stift'; symbolEditorZeichnen(); };
    gitter.append(b);
  });
  kasten.append(gitter);

  const zeile = SE('div', 'k-zeile');
  const w = document.createElement('input');
  w.type = 'color'; w.value = '#' + S.farbe;
  w.oninput = () => { S.farbe = w.value.slice(1); S.werkzeug = 'stift'; kopfSymbol(); };
  w.onchange = () => symbolEditorZeichnen();
  const t = document.createElement('input');
  t.type = 'text'; t.value = S.farbe; t.className = 's-hex';
  t.onchange = () => {
    const v = t.value.replace('#', '').trim();
    if (/^[0-9a-fA-F]{6}$/.test(v)) { S.farbe = v.toLowerCase(); }
    symbolEditorZeichnen();
  };
  zeile.append(w, t);
  kasten.append(zeile);

  // Alpha getrennt von der Farbe: 0 ist durchsichtig, 255 deckend. Zwischenwerte gehen,
  // sind auf einer LED-Matrix aber selten eine gute Idee — deshalb ohne Umschweife
  // ein Schieber mit Zahl daneben.
  const alpha = SE('label');
  alpha.append(SE('span', 'k-label', T('ui.deckkraft') + ': ' + S.alpha));
  const sch = document.createElement('input');
  sch.type = 'range'; sch.min = 0; sch.max = 255; sch.value = S.alpha;
  sch.oninput = () => {
    S.alpha = parseInt(sch.value, 10);
    alpha.querySelector('.k-label').textContent = T('ui.deckkraft') + ': ' + S.alpha;
  };
  alpha.append(sch);
  kasten.append(alpha);
  return kasten;
}

/* Wie es auf der Matrix aussieht: 1:1 und, weil dort nichts hinterleuchtet ist, auf
   schwarzem Grund. Das Schachbrett im Raster taugt zum Malen, nicht zum Beurteilen. */
function vorschauKasten() {
  const k = SE('div', 's-vorschau');
  k.append(SE('div', 'k-label', T('ui.wie_auf_der_matrix')));
  const c = document.createElement('canvas');
  c.id = 's-canvas'; c.width = S.breite; c.height = S.hoehe;
  c.style.width = (S.breite * 4) + 'px';
  c.style.height = (S.hoehe * 4) + 'px';
  k.append(c);
  setTimeout(vorschauAktualisieren, 0);
  return k;
}

function vorschauAktualisieren() {
  const c = document.getElementById('s-canvas');
  if (!c) return;
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, c.width, c.height);
  for (let i = 0; i < S.punkte.length; i++) {
    const p = S.punkte[i];
    const a = parseInt(p.slice(6, 8), 16);
    if (!a) continue;
    ctx.fillStyle = `rgba(${parseInt(p.slice(0,2),16)},${parseInt(p.slice(2,4),16)},` +
                    `${parseInt(p.slice(4,6),16)},${a / 255})`;
    ctx.fillRect(i % S.breite, Math.floor(i / S.breite), 1, 1);
  }
}

function fusszeile() {
  const z = SE('div', 'k-zeile');

  const name = document.createElement('input');
  name.type = 'text'; name.value = S.name; name.placeholder = T('ui.symbolname');
  name.oninput = () => { S.name = name.value.trim(); };
  z.append(name);

  const speichern = SE('button', 'k-knopf k-haupt', T('ui.speichern'));
  speichern.onclick = () => symbolSpeichern();
  z.append(speichern);

  if (S.eigen && S.offen) {
    const weg = SE('button', 'k-knopf k-gefahr', T('ui.loeschen'));
    weg.onclick = () => symbolLoeschen(S.offen);
    z.append(weg);
  }

  const meldung = SE('div', 'k-meldung');
  meldung.id = 's-meldung';
  meldung.style.display = 'none';

  const huelle = SE('div');
  huelle.append(z, groessenwahl(), meldung);
  return huelle;
}

function groessenwahl() {
  const z = SE('div', 'k-zeile');
  z.append(SE('span', 'k-label', T('ui.groesse')));
  [[8, 8], [8, 16], [16, 16], [9, 8], [32, 8]].forEach(([b, h]) => {
    const k = SE('button', 'k-knopf' + (b === S.breite && h === S.hoehe ? ' k-haupt' : ''),
                 `${b}×${h}`);
    k.onclick = () => groesseAendern(b, h);
    z.append(k);
  });
  return z;
}

/* Beim Umstellen der Größe bleibt das Gemalte erhalten, soweit es passt — abschneiden ist
   ärgerlich, aber alles wegzuwerfen wäre schlimmer. */
function groesseAendern(b, h) {
  merken();
  const alt = S.punkte, ab = S.breite;
  const neu = leer(b, h);
  for (let y = 0; y < Math.min(h, S.hoehe); y++) {
    for (let x = 0; x < Math.min(b, ab); x++) neu[y * b + x] = alt[y * ab + x];
  }
  S.breite = b; S.hoehe = h; S.punkte = neu; S.schmutzig = true;
  symbolEditorZeichnen();
}

function sMeldung(text, gut) {
  const m = document.getElementById('s-meldung');
  if (!m) return;
  m.className = 'k-meldung ' + (gut ? 'k-gut' : 'k-fehler');
  m.textContent = text;
  m.style.display = text ? '' : 'none';
}

async function symbolSpeichern() {
  if (!S.name) { sMeldung(T('ui.symbolname_fehlt')); return; }
  const a = await fetch('api/icons', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name: S.name, breite: S.breite, hoehe: S.hoehe,
                           punkte: S.punkte }),
  });
  const d = await a.json();
  if (!d.ok) { sMeldung(d.meldung || T('ui.fehler')); return; }
  S.offen = d.name; S.eigen = true; S.schmutzig = false;
  K.symbole = d.symbole;                 // das Bildergitter im Konfigurator zieht mit
  K.symbolMarke = (K.symbolMarke || 0) + 1;   // sonst zeigt der Browser das alte Bild
  // Formular UND Vorschau des Konfigurators zeigen das Symbol — beide muessen mit.
  if (typeof formularZeichnen === 'function') formularZeichnen();
  if (typeof vorschauHolen === 'function') vorschauHolen();
  sMeldung(T('ui.symbol_gespeichert') + ' ' + d.name, true);
  symbolListeZeichnen();
  symbolEditorZeichnen();
}

async function symbolLoeschen(name) {
  const a = await fetch('api/icons/' + encodeURIComponent(name), { method: 'DELETE' });
  const d = await a.json();
  if (!d.ok) { sMeldung(d.meldung || T('ui.fehler')); return; }
  K.symbole = d.symbole;
  K.symbolMarke = (K.symbolMarke || 0) + 1;
  if (typeof formularZeichnen === 'function') formularZeichnen();
  if (typeof vorschauHolen === 'function') vorschauHolen();
  S.offen = null; S.eigen = false;
  sMeldung(T('ui.symbol_geloescht'), true);
  symbolListeZeichnen();
  symbolEditorZeichnen();
}

async function symbolOeffnen(name) {
  if (S.schmutzig && !confirm(T('ui.verwerfen_frage'))) return;
  const d = await (await fetch(`api/icons/${encodeURIComponent(name)}/punkte`)).json();
  S.breite = d.breite; S.hoehe = d.hoehe; S.punkte = d.punkte;
  S.name = d.name; S.offen = d.name; S.eigen = d.eigen;
  S.schmutzig = false; S.rueckgaengig = [];
  sMeldung('');
  symbolListeZeichnen();
  symbolEditorZeichnen();
}

function symbolNeu() {
  if (S.schmutzig && !confirm(T('ui.verwerfen_frage'))) return;
  S.punkte = leer(S.breite, S.hoehe);
  S.name = ''; S.offen = null; S.eigen = false;
  S.schmutzig = false; S.rueckgaengig = [];
  sMeldung('');
  symbolListeZeichnen();
  symbolEditorZeichnen();
}

function symbolListeZeichnen() {
  const ziel = document.getElementById('s-liste');
  if (!ziel) return;
  ziel.innerHTML = '';

  const neu = SE('button', 'k-knopf', '+ ' + T('ui.neues_symbol'));
  neu.onclick = symbolNeu;
  ziel.append(neu);

  const gitter = SE('div', 'k-symbolgitter');
  (K.symbole || []).forEach(name => {
    const b = document.createElement('img');
    b.src = 'api/icons/' + encodeURIComponent(name) + `.png?zoom=5&t=${K.symbolMarke || 0}`;
    b.title = name;
    if (name === S.offen) b.className = 'aktiv';
    b.onclick = () => symbolOeffnen(name);
    gitter.append(b);
  });
  ziel.append(gitter);
}

function kopfSymbol() { /* Platzhalter: der Kopf zeigt nichts Eigenes */ }
