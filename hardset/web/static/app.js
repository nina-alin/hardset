'use strict';

// État de la page. Le set courant vit ici : le serveur n'en garde pas de copie.
const state = {
  config: null,
  collection: null,
  set: null,
  path: '',
  // Sons imposés aux extrémités, tels que /api/tracks les a rendus (ou null).
  pins: { start: null, end: null },
};
window.state = state;

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, enfants = []) {
  const noeud = Object.assign(document.createElement(tag), props);
  for (const enfant of enfants) noeud.append(enfant);
  return noeud;
}

// Met en forme le "detail" d'une réponse d'erreur de l'API. Les erreurs métier
// renvoient une chaîne française directement affichable ; les erreurs de
// validation de FastAPI renvoient une liste d'objets, qu'il ne faut jamais
// afficher telle quelle (sans quoi on obtient "[object Object]").
function messageErreur(detail) {
  if (typeof detail === 'string' && detail) return detail;
  return 'requête invalide : vérifiez les valeurs saisies';
}

async function api(route, corps) {
  const reponse = await fetch(route, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(corps),
  });
  if (!reponse.ok) {
    const donnees = await reponse.json().catch(() => ({ detail: reponse.statusText }));
    throw new Error(messageErreur(donnees.detail));
  }
  return reponse;
}

// Désactive le ou les boutons donnés le temps de l'action asynchrone, pour
// empêcher qu'un double-clic ne déclenche deux appels réseau concurrents sur
// le même état. Les erreurs sont affichées comme avertissement. Rend `true` si
// l'action est allée au bout, pour les appelants qui ont autre chose à ranger.
async function proteger(boutons, action) {
  const liste = Array.isArray(boutons) ? boutons : [boutons];
  for (const bouton of liste) bouton.disabled = true;
  try {
    await action();
    return true;
  } catch (erreur) {
    renderAvertissements([{ message: erreur.message }]);
    return false;
  } finally {
    for (const bouton of liste) bouton.disabled = false;
  }
}

// --- Lecture du formulaire ------------------------------------------------

function cochees(conteneur) {
  return [...conteneur.querySelectorAll('input:checked')].map((c) => c.value);
}

function requete(extra = {}) {
  return {
    path: state.path,
    genres: cochees($('genres')),
    moods: cochees($('moods')).map(Number),
    bpm_min: Number($('bpm-min').value),
    bpm_max: Number($('bpm-max').value),
    profile: $('profile').value,
    duration_min: Number($('duration').value),
    seconds_per_track: Number($('seconds').value),
    start_track_id: state.pins.start ? state.pins.start.id : null,
    end_track_id: state.pins.end ? state.pins.end.id : null,
    ...extra,
  };
}

// --- Rendu ----------------------------------------------------------------

function renderAvertissements(avertissements) {
  const zone = $('avertissements');
  zone.replaceChildren();
  zone.hidden = !avertissements.length;
  for (const a of avertissements) {
    zone.append(el('div', { className: 'avertissement', textContent: a.message }));
  }
}

// Un morceau peut porter plusieurs moods : `track.mood` est alors leur moyenne
// (2,5 par exemple), qui ne correspond à aucun libellé. On étiquette donc à
// partir de `track.moods`, les niveaux réellement tagués, et on n'affiche la
// moyenne que lorsqu'elle s'en distingue.
function moodLabel(track) {
  const niveaux = track.moods ?? [];
  if (!niveaux.length) return '—';
  const libelles = niveaux.map((v) => {
    const mood = state.config.moods.find((m) => m.value === v);
    return mood ? mood.label : String(v);
  });
  if (niveaux.length === 1) return `${niveaux[0]} ${libelles[0]}`;
  return `${formateMood(track.mood)} ${libelles.join(' + ')}`;
}

// 3 plutôt que « 3.0 », mais 2,5 conservé : la moyenne de deux moods voisins
// est l'information utile, pas un arrondi qui la ferait passer pour un niveau.
function formateMood(valeur) {
  return Number.isInteger(valeur) ? String(valeur) : valeur.toFixed(1);
}

// Le repère suit le morceau épinglé s'il est déplacé : il est posé par
// comparaison d'id, jamais par position. Les boutons de la ligne restent
// actifs — l'épinglage contraint la génération, il ne verrouille pas l'édition.
function celluleNumero(track, index) {
  const epingle = [state.pins.start, state.pins.end].some((p) => p && p.id === track.id);
  return epingle
    ? { textContent: `${index + 1} 📌`, title: 'son choisi avant la génération' }
    : { textContent: String(index + 1) };
}

function render() {
  const jeu = state.set;
  $('resultat').hidden = !jeu;
  $('regenerer').hidden = !jeu;
  // Le bouton d'export reste inactif tant qu'il n'y a pas de set, ou que le
  // set affiché ne contient plus aucun morceau (toutes les lignes supprimées).
  $('exporter').disabled = !jeu || jeu.tracks.length === 0;
  const corps = $('tracklist').querySelector('tbody');
  if (!jeu) {
    // Pas de set (au démarrage, ou après le chargement d'une nouvelle
    // collection) : la tracklist ne doit garder aucune ligne périmée, et la
    // courbe BPM (qui décrit ce set précis) ne doit pas rester affichée avec
    // les données de la collection précédente.
    corps.replaceChildren();
    window.renderCurve(null, []);
    return;
  }

  $('compteur').textContent = `${jeu.tracks.length} morceaux`;
  corps.replaceChildren();

  jeu.tracks.forEach((track, index) => {
    const actions = el('td', { className: 'actions' }, [
      el('button', {
        type: 'button', textContent: '↑', title: 'monter',
        disabled: index === 0,
        onclick: () => deplacer(index, -1),
      }),
      el('button', {
        type: 'button', textContent: '↓', title: 'descendre',
        disabled: index === jeu.tracks.length - 1,
        onclick: () => deplacer(index, 1),
      }),
      el('button', {
        type: 'button', textContent: '⟳', title: 'remplacer',
        onclick: (evenement) => remplacer(index, evenement.currentTarget),
      }),
      el('button', {
        type: 'button', textContent: '✕', title: 'supprimer',
        onclick: (evenement) => supprimer(index, evenement.currentTarget),
      }),
    ]);

    corps.append(el('tr', {}, [
      el('td', celluleNumero(track, index)),
      el('td', { textContent: track.artist }),
      el('td', { textContent: track.title }),
      el('td', { textContent: track.bpm.toFixed(1) }),
      el('td', { textContent: track.camelot ?? '—' }),
      el('td', { textContent: moodLabel(track) }),
      el('td', { textContent: track.genres.join(', ') }),
      actions,
    ]));
  });

  renderAvertissements(jeu.warnings);
  window.renderCurve(jeu.targets, jeu.tracks);
}

// --- Sons de départ et de fin ---------------------------------------------
//
// Un son choisi impose la borne de BPM correspondante. La page écrit la valeur
// dans le champ et le verrouille, mais ce n'est que de l'affichage : le serveur
// re-dérive toujours la borne depuis l'id envoyé et ne lit jamais ce que le
// champ a transmis (hardset/engine/pinning.py).

const PINS = {
  start: { bpm: 'bpm-min', note: 'note-bpm-min', borne: (b) => b.min },
  end:   { bpm: 'bpm-max', note: 'note-bpm-max', borne: (b) => b.max },
};

const minuteries = { start: null, end: null };

// Bornes de BPM de la collection chargée, celles que le champ retrouve quand on
// retire un son choisi. Sans collection, les valeurs par défaut du formulaire.
function bornesCollection() {
  const lue = state.collection;
  if (!lue || !(lue.bpm_max > 0)) return { min: 150, max: 200 };
  return { min: Math.floor(lue.bpm_min), max: Math.ceil(lue.bpm_max) };
}

function appliquerPin(role) {
  const pin = state.pins[role];
  const { bpm, note, borne } = PINS[role];
  const champ = $(`recherche-${role}`);
  const choix = $(`choix-${role}`);

  $(`resultats-${role}`).replaceChildren();
  $(`resultats-${role}`).hidden = true;
  choix.replaceChildren();
  choix.hidden = !pin;
  champ.hidden = Boolean(pin);

  if (pin) {
    choix.append(
      el('span', {
        className: 'epingle',
        textContent: `📌 ${pin.artist} — ${pin.title} · ${pin.bpm.toFixed(1)} BPM`,
      }),
      el('button', {
        type: 'button', textContent: '✕', title: 'retirer ce choix',
        onclick: () => { state.pins[role] = null; appliquerPin(role); },
      }),
    );
    $(bpm).value = pin.bpm;
  } else {
    champ.value = '';
    $(bpm).value = borne(bornesCollection());
  }
  $(bpm).readOnly = Boolean(pin);
  $(note).hidden = !pin;
}

function choisirPin(role, track) {
  const autre = role === 'start' ? 'end' : 'start';
  if (state.pins[autre] && state.pins[autre].id === track.id) {
    // Le serveur le refuserait aussi ; le dire tout de suite évite un
    // aller-retour pour une erreur visible d'ici.
    renderAvertissements([{
      message: 'le même morceau ne peut pas être à la fois le son de départ et le son de fin',
    }]);
    return;
  }
  state.pins[role] = track;
  appliquerPin(role);
}

async function rechercher(role) {
  const q = $(`recherche-${role}`).value.trim();
  const liste = $(`resultats-${role}`);
  if (!q) {
    liste.replaceChildren();
    liste.hidden = true;
    return;
  }
  try {
    const reponse = await api('/api/tracks', { path: state.path, q, limit: 20 });
    const donnees = await reponse.json();
    liste.replaceChildren(...donnees.tracks.map((track) => el('li', {}, [
      el('button', {
        type: 'button',
        textContent: `${track.artist} — ${track.title} · ${track.bpm.toFixed(1)} BPM · ${track.camelot ?? '—'}`,
        onclick: () => choisirPin(role, track),
      }),
    ])));
    if (!donnees.tracks.length) {
      liste.append(el('li', { className: 'discret', textContent: 'aucun morceau trouvé' }));
    } else if (donnees.truncated) {
      liste.append(el('li', {
        className: 'discret', textContent: 'affinez : d’autres morceaux correspondent',
      }));
    }
    liste.hidden = false;
  } catch (erreur) {
    renderAvertissements([{ message: erreur.message }]);
  }
}

// Une frappe ne déclenche pas un appel : la temporisation évite une requête par
// caractère sur une collection de plusieurs centaines de morceaux.
function brancherRecherche(role) {
  const champ = $(`recherche-${role}`);
  champ.oninput = () => {
    clearTimeout(minuteries[role]);
    minuteries[role] = setTimeout(() => rechercher(role), 200);
  };
  champ.onkeydown = (evenement) => {
    if (evenement.key === 'Escape') $(`resultats-${role}`).hidden = true;
  };
}

// --- Actions --------------------------------------------------------------

async function chargerCollection() {
  $('etat-collection').textContent = 'lecture…';
  // Un set affiché ne survit pas au chargement d'une autre collection : il ne
  // lui appartient plus, et le laisser à l'écran mènerait à des actions qui
  // échouent avec un message serveur correct mais déroutant.
  state.set = null;
  render();

  const charge = await proteger($('charger'), async () => {
    const reponse = await api('/api/collection', { path: $('path').value });
    const donnees = await reponse.json();
    state.collection = donnees;
    state.path = donnees.path;

    $('etat-collection').textContent = `${donnees.track_count} morceaux, ${donnees.genres.length} genres`;

    const zone = $('genres');
    zone.replaceChildren();
    zone.classList.remove('discret');
    for (const genre of donnees.genres) {
      zone.append(el('label', {}, [
        el('input', { type: 'checkbox', value: genre }),
        document.createTextNode(genre),
      ]));
    }

    // Les sons choisis n'appartiennent plus à cette collection-ci, comme le set.
    // `appliquerPin` remet du même coup les bornes de BPM de la collection lue.
    state.pins = { start: null, end: null };
    for (const role of ['start', 'end']) {
      $(`recherche-${role}`).disabled = false;
      appliquerPin(role);
    }

    $('generer').disabled = false;
    renderAvertissements(donnees.warnings);
  });

  // La lecture a échoué : `proteger` a déjà affiché l'erreur, il reste à
  // retirer le « lecture… » qui n'aboutira pas.
  if (!charge) $('etat-collection').textContent = '';
}

async function generer() {
  // « Générer » et « Régénérer » déclenchent tous les deux cette fonction : on
  // désactive les deux boutons ensemble, pour ne pas dépendre de savoir lequel
  // des deux a réellement reçu le clic.
  await proteger([$('generer'), $('regenerer')], async () => {
    const reponse = await api('/api/generate', requete());
    state.set = await reponse.json();
    $('nom-playlist').value = state.set.playlist_name;
    render();
  });
}

async function remplacer(index, bouton) {
  await proteger(bouton, async () => {
    const ids = state.set.tracks.map((t) => t.id);
    const reponse = await api('/api/replace', requete({ track_ids: ids, position: index }));
    state.set = await reponse.json();
    render();
  });
}

async function supprimer(index, bouton) {
  state.set.tracks.splice(index, 1);
  // Rendu immédiat : sans lui, le tableau affiche encore les anciennes lignes
  // — avec les anciens index capturés dans leurs gestionnaires de clic —
  // pendant tout l'aller-retour serveur qui suit, et un clic sur une autre
  // ligne pendant cette fenêtre agirait alors sur le mauvais morceau.
  render();
  // Les cibles appartiennent au serveur, qui les redistribue sur la nouvelle
  // longueur. Les tronquer ici afficherait une courbe cible fausse — plus basse
  // que l'obtenu, donnant à voir un dépassement de BPM qui n'existe pas — et
  // reviendrait à laisser le navigateur décider de la forme de la courbe
  // d'énergie, ce qui est de la logique musicale.
  await proteger(bouton, async () => {
    const reponse = await api('/api/targets', requete({ count: state.set.tracks.length }));
    state.set.targets = (await reponse.json()).targets;
    render();
  });
}

function deplacer(index, delta) {
  const tracks = state.set.tracks;
  const cible = index + delta;
  [tracks[index], tracks[cible]] = [tracks[cible], tracks[index]];
  render();
}

async function exporter() {
  await proteger($('exporter'), async () => {
    const reponse = await api('/api/export', {
      path: state.path,
      track_ids: state.set.tracks.map((t) => t.id),
      playlist_name: $('nom-playlist').value,
    });
    const blob = await reponse.blob();
    const lien = el('a', {
      href: URL.createObjectURL(blob),
      download: `${$('nom-playlist').value || 'set'}.xml`,
    });
    document.body.append(lien);
    lien.click();
    lien.remove();
    URL.revokeObjectURL(lien.href);
  });
}

// --- Démarrage ------------------------------------------------------------

async function init() {
  state.config = await (await fetch('/api/config')).json();

  $('profile').replaceChildren(
    ...state.config.profils.map((p) => el('option', { value: p.key, textContent: p.label })),
  );

  $('moods').replaceChildren(
    ...state.config.moods.map((m) => el('label', {}, [
      el('input', { type: 'checkbox', value: String(m.value) }),
      document.createTextNode(`${m.value} — ${m.label}`),
    ])),
  );

  $('seconds').value = state.config.seconds_per_track;
  if (state.config.collection_xml) $('path').value = state.config.collection_xml;

  for (const role of ['start', 'end']) brancherRecherche(role);

  $('charger').onclick = chargerCollection;
  $('generer').onclick = generer;
  $('regenerer').onclick = generer;
  $('exporter').onclick = exporter;

  document.addEventListener('click', (evenement) => {
    if (evenement.target.closest('.recherche')) return;
    for (const role of ['start', 'end']) $(`resultats-${role}`).hidden = true;
  });
}

init();
