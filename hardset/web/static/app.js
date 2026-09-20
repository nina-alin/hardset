'use strict';

// État de la page. Le set courant vit ici : le serveur n'en garde pas de copie.
const state = {
  config: null,
  collection: null,
  set: null,
  path: '',
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
// le même état. Les erreurs sont affichées comme avertissement.
async function proteger(boutons, action) {
  const liste = Array.isArray(boutons) ? boutons : [boutons];
  for (const bouton of liste) bouton.disabled = true;
  try {
    await action();
  } catch (erreur) {
    renderAvertissements([{ message: erreur.message }]);
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

function moodLabel(valeur) {
  const mood = state.config.moods.find((m) => m.value === valeur);
  return mood ? `${valeur} ${mood.label}` : String(valeur ?? '—');
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
    // collection) : la tracklist ne doit garder aucune ligne périmée.
    corps.replaceChildren();
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
        onclick: () => supprimer(index),
      }),
    ]);

    corps.append(el('tr', {}, [
      el('td', { textContent: String(index + 1) }),
      el('td', { textContent: track.artist }),
      el('td', { textContent: track.title }),
      el('td', { textContent: track.bpm.toFixed(1) }),
      el('td', { textContent: track.camelot ?? '—' }),
      el('td', { textContent: moodLabel(track.mood) }),
      el('td', { textContent: track.genres.join(', ') }),
      actions,
    ]));
  });

  renderAvertissements(jeu.warnings);
}

// --- Actions --------------------------------------------------------------

async function chargerCollection() {
  const bouton = $('charger');
  bouton.disabled = true;
  $('etat-collection').textContent = 'lecture…';
  // Un set affiché ne survit pas au chargement d'une autre collection : il ne
  // lui appartient plus, et le laisser à l'écran mènerait à des actions qui
  // échouent avec un message serveur correct mais déroutant.
  state.set = null;
  render();
  try {
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

    if (donnees.bpm_max > 0) {
      $('bpm-min').value = Math.floor(donnees.bpm_min);
      $('bpm-max').value = Math.ceil(donnees.bpm_max);
    }

    $('generer').disabled = false;
    renderAvertissements(donnees.warnings);
  } catch (erreur) {
    $('etat-collection').textContent = '';
    renderAvertissements([{ message: erreur.message }]);
  } finally {
    bouton.disabled = false;
  }
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

function supprimer(index) {
  state.set.tracks.splice(index, 1);
  state.set.targets = state.set.targets.slice(0, state.set.tracks.length);
  render();
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

  $('charger').onclick = chargerCollection;
  $('generer').onclick = generer;
  $('regenerer').onclick = generer;
  $('exporter').onclick = exporter;
}

init();
