'use strict';

// Courbe BPM : cible contre obtenu, position par position. Le but est de voir
// immédiatement si la collection a imposé un creux ou un palier subi.

const SVG_NS = 'http://www.w3.org/2000/svg';
const LARGEUR = 900;
const HAUTEUR = 260;
const MARGE = { haut: 16, droite: 16, bas: 28, gauche: 44 };

function noeud(tag, attrs) {
  const element = document.createElementNS(SVG_NS, tag);
  for (const [cle, valeur] of Object.entries(attrs)) element.setAttribute(cle, valeur);
  return element;
}

function renderCurve(targets, tracks) {
  const conteneur = document.getElementById('courbe-svg');
  const section = document.getElementById('courbe');
  conteneur.replaceChildren();

  if (!targets || targets.length < 2) {
    section.hidden = true;
    return;
  }
  section.hidden = false;

  const bpms = [...targets.map((c) => c.bpm), ...tracks.map((t) => t.bpm)];
  const basse = Math.floor(Math.min(...bpms) - 2);
  const haute = Math.ceil(Math.max(...bpms) + 2);

  const x = (i) => MARGE.gauche
    + (i / (targets.length - 1)) * (LARGEUR - MARGE.gauche - MARGE.droite);
  const y = (bpm) => HAUTEUR - MARGE.bas
    - ((bpm - basse) / (haute - basse || 1)) * (HAUTEUR - MARGE.haut - MARGE.bas);

  const svg = noeud('svg', {
    viewBox: `0 0 ${LARGEUR} ${HAUTEUR}`,
    width: '100%',
    height: HAUTEUR,
    role: 'img',
    'aria-label': 'BPM cible et BPM obtenu par position',
  });

  // Graduations horizontales, tous les 10 BPM.
  for (let bpm = Math.ceil(basse / 10) * 10; bpm <= haute; bpm += 10) {
    svg.append(noeud('line', {
      x1: MARGE.gauche, x2: LARGEUR - MARGE.droite,
      y1: y(bpm), y2: y(bpm),
      stroke: '#2c313a', 'stroke-width': 1,
    }));
    const etiquette = noeud('text', {
      x: MARGE.gauche - 8, y: y(bpm) + 4,
      fill: '#9aa1ab', 'font-size': 11, 'text-anchor': 'end',
    });
    etiquette.textContent = String(bpm);
    svg.append(etiquette);
  }

  const chemin = (valeurs) => valeurs
    .map((bpm, i) => `${i === 0 ? 'M' : 'L'}${x(i).toFixed(1)},${y(bpm).toFixed(1)}`)
    .join(' ');

  // Cible en pointillé, obtenu en plein : l'écart entre les deux est l'information.
  svg.append(noeud('path', {
    d: chemin(targets.map((c) => c.bpm)),
    fill: 'none', stroke: '#9aa1ab', 'stroke-width': 1.5, 'stroke-dasharray': '5 4',
  }));
  svg.append(noeud('path', {
    d: chemin(tracks.map((t) => t.bpm)),
    fill: 'none', stroke: '#ff5c35', 'stroke-width': 2,
  }));

  tracks.forEach((track, i) => {
    const point = noeud('circle', { cx: x(i), cy: y(track.bpm), r: 3, fill: '#ff5c35' });
    const titre = noeud('title', {});
    titre.textContent = `${i + 1}. ${track.artist} — ${track.title} (${track.bpm.toFixed(1)} BPM)`;
    point.append(titre);
    svg.append(point);
  });

  const legende = noeud('text', {
    x: MARGE.gauche, y: HAUTEUR - 6, fill: '#9aa1ab', 'font-size': 11,
  });
  legende.textContent = '— — cible      ——— obtenu';
  svg.append(legende);

  conteneur.append(svg);
}

window.renderCurve = renderCurve;
