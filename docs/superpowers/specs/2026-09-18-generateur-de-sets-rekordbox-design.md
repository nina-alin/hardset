# Générateur automatique de sets DJ à partir des tags Rekordbox

Date : 2026-09-18
Statut : design validé, prêt pour planification

## 1. Objectif

Construire automatiquement une playlist Rekordbox exploitable comme set DJ hardcore /
techno, à partir des My Tags déjà posés sur la collection.

L'utilisatrice décrit le set qu'elle veut (genres, plage de BPM, moods, profil
d'évolution, durée) ; l'outil sélectionne et ordonne les morceaux, affiche le résultat
pour édition, puis exporte une playlist réimportable dans Rekordbox.

## 2. Périmètre

Dans le périmètre :

- lecture d'un export XML de collection Rekordbox, My Tags compris ;
- filtrage par genre, mood et BPM ;
- ordonnancement suivant un profil d'évolution nommé (BPM et mood) ;
- préférence harmonique entre morceaux consécutifs (roue Camelot) ;
- interface web locale avec tracklist éditable et courbe BPM ;
- export d'un XML Rekordbox contenant la playlist du set.

Hors périmètre (décidé explicitement) :

- écriture dans la base Rekordbox (`master.db`) : l'outil ne modifie jamais la
  bibliothèque, il produit un fichier à importer ;
- historique des sets joués et pénalisation des morceaux récemment utilisés ;
- analyse audio des fichiers (l'outil fait confiance aux métadonnées Rekordbox) ;
- recherche d'un ordonnancement optimal global ;
- gestion du demi / double tempo ;
- tests automatisés de l'interface web.

## 3. Décisions actées

| Sujet | Décision | Raison |
|---|---|---|
| Source des tags | My Tag Rekordbox | C'est la classification déjà en place |
| Canal d'entrée/sortie | XML exporté → XML importé | Aucun risque pour la base, entièrement réversible |
| Pilotage de l'évolution | Profils de courbe nommés | Correspond à la façon dont un set se pense |
| Tonalité | Critère secondaire | La courbe d'énergie prime en hardcore |
| Interface | UI web locale | Édition de la tracklist avant export |
| Variation | Aléatoire simple, sans mémoire | Suffisant, et évite un sous-système de persistance |
| Durée | Temps de jeu moyen configurable, défaut 2 min | Les morceaux sont joués courts, la durée réelle du fichier n'est pas pertinente |

## 4. Architecture

Quatre couches, avec une frontière stricte entre la logique musicale et la technique.

| Module | Responsabilité | Dépend de |
|---|---|---|
| `hardset/model.py` | `Track`, `Mood`, `SetRequest`, `GeneratedSet`, `Warning` | rien |
| `hardset/rekordbox/` | Parsing du XML de collection, écriture du XML de playlist | `model` |
| `hardset/engine/` | Courbes, filtrage, scoring, séquençage | `model` |
| `hardset/config.py` | Chargement de la configuration YAML (moods, profils, poids) | `model` |
| `hardset/web/` | Serveur FastAPI + page unique HTML/JS | tous les précédents |

`engine/` et `model.py` sont du Python pur : aucune entrée/sortie fichier, aucun réseau,
aucun état global. C'est ce qui rend le comportement musical vérifiable par des tests
rapides sur des collections fabriquées.

`engine/` se décompose en :

- `curves.py` — traduit un profil et une durée en une liste de cibles (BPM, mood) ;
- `filtering.py` — réduit la collection aux morceaux éligibles ;
- `harmony.py` — conversion des tonalités en Camelot et pénalité de transition ;
- `sequencing.py` — le remplissage position par position.

### Stack

Python 3.12+, FastAPI + uvicorn, PyYAML, pytest. Front-end en HTML et JavaScript
vanilla servi par FastAPI : pas d'étape de build, pas de dépendance CDN. La courbe BPM
est un SVG dessiné directement en JavaScript.

## 5. Modèle de données

### Track

| Champ | Source XML | Notes |
|---|---|---|
| `id` | `TrackID` | clé de référence dans la playlist exportée |
| `artist` | `Artist` | |
| `title` | `Name` | |
| `bpm` | `AverageBpm` | flottant |
| `camelot` | `Tonality` | normalisé (voir §7), `None` si absent ou illisible |
| `duration_s` | `TotalTime` | conservé pour information, non utilisé pour la durée du set |
| `location` | `Location` | recopié tel quel à l'export |
| `genres` | My Tags | liste, éventuellement vide |
| `mood` | My Tags | valeur unique 1→5, `None` si absente |
| `raw_attrs` | attributs du nœud `TRACK` | recopiés intégralement à l'export |
| `raw_children` | nœuds enfants du `TRACK` — beatgrid (`TEMPO`), points de repère (`POSITION_MARK`) | fragments sérialisés, recopiés tels quels à l'export |

`raw_attrs` et `raw_children` sont conservés pour que l'export puisse reproduire le
nœud `TRACK` d'origine sans perte : l'outil n'a pas à comprendre tous les attributs
ni tous les nœuds enfants Rekordbox pour les restituer.

### Mood

Échelle ordinale fermée, définie dans la configuration et non dans le code :

```
1 calme · 2 dansant · 3 un peu vénère · 4 vénère · 5 c'est du bruit
```

Un morceau porte **un seul** mood. Un morceau portant plusieurs tags de mood est conservé
dans la collection mais exclu de la sélection, et signalé dans les avertissements. Un
morceau sans mood est également exclu de la sélection et signalé.

Un morceau porte **zéro ou plusieurs** genres.

### SetRequest

```
genres: set[str]          # vide = tous
moods: set[int]           # vide = tous
bpm_min, bpm_max: float
profile: str              # clé d'un profil de la configuration
duration_min: int
seconds_per_track: int    # défaut 120
seed: int | None          # non exposé dans l'interface, sert aux tests
```

`seed` n'apparaît pas dans le formulaire : il n'existe que pour rendre la génération
reproductible dans les tests. En usage normal il vaut `None` et chaque génération diffère.

### GeneratedSet

```
tracks: list[Track]       # dans l'ordre de jeu
targets: list[Target]     # cible (bpm, mood) de chaque position, pour la courbe
warnings: list[Warning]
```

## 6. Lecture du XML et des My Tags

Rekordbox écrit les My Tags dans l'attribut `Comments` du nœud `TRACK`, sous la forme
`/* tag / tag / tag */`, éventuellement précédés ou suivis d'un commentaire libre.
Le XML ne transporte **pas** la catégorie My Tag à laquelle chaque tag appartient.

La distinction genre / mood se fait donc par la configuration :

```yaml
moods:          # l'ordre définit l'échelle ordinale
  - calme
  - dansant
  - un peu vénère
  - vénère
  - c'est du bruit
```

Tout tag reconnu dans cette liste devient le mood du morceau. **Tout autre tag est traité
comme un genre.** Aucune liste de genres n'a donc à être maintenue : l'interface propose
les genres réellement présents dans l'export.

La comparaison des tags est insensible à la casse, aux accents et aux espaces de bordure.

### Risque à lever en premier

Le format exact (`/* ... */`, séparateur, présence effective des My Tags à l'export) doit
être vérifié sur un export réel **avant toute autre implémentation**. Si les My Tags ne
sont pas exploitables depuis le XML, la solution de repli est la lecture de `master.db`
via `pyrekordbox` ; cela ne remplacerait que `hardset/rekordbox/reader.py`, le reste du
design étant inchangé.

## 7. Tonalité

`Tonality` peut contenir une notation classique (`Am`, `F#m`, `C`), Camelot (`8A`) ou
Open Key (`1m`) selon les préférences Rekordbox. L'outil normalise tout en Camelot
(`1A`–`12B`). Une valeur vide ou non reconnue donne `camelot = None`, sans écarter le
morceau.

Pénalité de transition entre le morceau précédent et le candidat :

| Relation | Pénalité |
|---|---|
| Même clé | 0 |
| Voisin sur la roue (±1, même lettre) | 0 |
| Relatif majeur / mineur (même chiffre, autre lettre) | 0 |
| ±2 sur la roue | 1 |
| Tout autre cas | 2 |
| Une des deux clés inconnue | 0,5 |

La pénalité ne porte que sur la transition immédiate : l'outil ne cherche pas à maintenir
une tonalité sur la durée, il favorise des enchaînements deux à deux.

## 8. Génération

### Étape 1 — Filtrage

Sont éligibles les morceaux dont le mood est défini et unique, dont le mood appartient aux
moods demandés, dont au moins un genre appartient aux genres demandés, et
dont le BPM est dans la plage. Si aucun genre n'est demandé, le critère de genre n'est pas
appliqué du tout — un morceau sans aucun genre reste éligible.

Soit `N = duration_min * 60 / seconds_per_track` le nombre de morceaux visé. Si le nombre
de morceaux éligibles est inférieur à `N`, **l'outil produit le set le plus long possible**
et émet un avertissement (`45 morceaux demandés, 28 éligibles`). Ce n'est pas une erreur.

### Étape 2 — Cibles

Le profil fournit deux fonctions de progression `p(t) → [0,1]` pour `t ∈ [0,1]`, l'une
pour le BPM, l'autre pour le mood. Pour la position `i` sur `N` :

```
t           = i / max(N - 1, 1)
bpm_cible   = bpm_min + p_bpm(t)  * (bpm_max - bpm_min)
mood_cible  = mood_min + p_mood(t) * (mood_max - mood_min)
```

`mood_min` et `mood_max` sont les bornes des moods demandés, ou 1 et 5 si aucun mood
n'est demandé. `mood_cible` est un flottant,
volontairement non arrondi : un set peut viser « entre dansant et un peu vénère ».

### Étape 3 — Remplissage

Pour chaque position, dans l'ordre, chaque morceau encore disponible reçoit un coût :

```
coût =   w_bpm  * |bpm - bpm_cible| / bpm_tolerance
       + w_mood * |mood - mood_cible|
       + w_key  * pénalité_harmonique(précédent, candidat)
```

Le morceau retenu est **tiré uniformément parmi les `k` de coût le plus faible**, puis
retiré du pool. C'est la seule source d'aléa : la courbe est toujours respectée, mais deux
générations successives donnent des sets différents. La première position n'a pas de
prédécesseur : la pénalité harmonique y vaut 0.

Valeurs par défaut, toutes dans la configuration :

```yaml
poids:
  bpm: 1.0
  mood: 1.5
  tonalite: 0.4
  bpm_tolerance: 5.0   # un écart de 5 BPM coûte 1 unité avant pondération
  k: 5                 # largeur du tirage
```

L'algorithme est glouton et ne revient jamais en arrière. Il peut donc consommer tôt un
morceau qui aurait mieux servi plus tard. C'est accepté : sur une collection de quelques
centaines de titres l'effet est inaudible, et la tracklist reste éditable.

### Remplacement d'un morceau

L'action « remplacer » de l'interface rejoue l'étape 3 pour cette seule position, avec le
même calcul de coût, en excluant les morceaux déjà présents dans le set. Le voisin
précédent est le morceau effectivement en place.

## 9. Profils

Les profils sont définis en configuration. Trois types de courbe paramétriques, pas de
code arbitraire :

| Type | Formule | Paramètres |
|---|---|---|
| `lineaire` | `depart + t * (arrivee - depart)` | `depart` (0), `arrivee` (1) |
| `retarde` | `0` si `t < palier`, sinon `(t - palier) / (1 - palier)` | `palier` |
| `vagues` | `clamp(t + amplitude * sin(2π * oscillations * t), 0, 1)` | `amplitude`, `oscillations` |

Les quatre profils livrés :

```yaml
profils:
  montee:
    label: "Montée"
    bpm:  {type: lineaire}
    mood: {type: lineaire}
  warmup-long:
    label: "Warm-up long"
    bpm:  {type: retarde, palier: 0.4}
    mood: {type: retarde, palier: 0.4}
  plateau:
    label: "Plateau"
    bpm:  {type: lineaire, depart: 0.7}
    mood: {type: lineaire, depart: 0.7}
  vagues:
    label: "Vagues"
    bpm:  {type: vagues, amplitude: 0.15, oscillations: 2.5}
    mood: {type: lineaire}
```

Ajouter un profil ne demande aucune modification de code.

## 10. Interface web

Page unique, servie en local, ouverte automatiquement au lancement.

**Formulaire** — chemin du XML de collection, lu côté serveur (tout tourne en local sur
la machine ; le chemin par défaut est dans la configuration) ; cases à cocher des genres (alimentées par
les tags réellement présents) ; cases à cocher des moods ; plage BPM ; profil ; durée en
minutes ; temps de jeu par morceau (défaut 120 s).

**Courbe BPM** — SVG superposant le BPM cible et le BPM obtenu, position par position.
Permet de voir immédiatement si la collection a imposé un creux ou un palier subi.

**Tracklist** — position, artiste, titre, BPM, clé Camelot, mood, genres. Trois actions par
ligne : supprimer, remplacer, déplacer. Un bouton « régénérer » relance la génération
complète.

**Avertissements** — bandeau listant les problèmes rencontrés : pénurie de morceaux,
morceaux sans tonalité analysée, morceaux à moods multiples, morceaux sans mood.

**Export** — champ « nom de la playlist », prérempli `{genres}-{profil}-{durée}min-{date}`,
et un bouton déclenchant le téléchargement du fichier XML par le navigateur.

## 11. Export XML

Le fichier produit respecte la structure `DJ_PLAYLISTS` :

```xml
<DJ_PLAYLISTS Version="1.0.0">
  <PRODUCT Name="rekordbox" Version="6.0.0" Company="AlphaTheta"/>
  <COLLECTION Entries="N"> ... nœuds TRACK du set ... </COLLECTION>
  <PLAYLISTS>
    <NODE Type="0" Name="ROOT" Count="1">
      <NODE Name="..." Type="1" KeyType="0" Entries="N">
        <TRACK Key="TrackID"/> ...
      </NODE>
    </NODE>
  </PLAYLISTS>
</DJ_PLAYLISTS>
```

Rekordbox exige que tout morceau référencé dans une playlist figure dans le bloc
`COLLECTION` du même fichier ; les nœuds `TRACK` sont donc recopiés depuis `raw_attrs`,
sans aucune modification. L'import est additif : supprimer la playlist importée dans
Rekordbox ne laisse aucune trace.

## 12. Tests

Le moteur étant pur, il se teste sur des collections fabriquées en mémoire.

| Test | Vérifie |
|---|---|
| Montée sur collection idéale | Le BPM obtenu suit la cible à `bpm_tolerance` près |
| Progression du mood | Le mood moyen du premier tiers est inférieur à celui du dernier tiers |
| Pénurie | 28 morceaux pour 45 demandés : set de 28 + avertissement, pas d'exception |
| Collection sans tonalité | Le set est généré, pénalité neutre appliquée |
| Profil vagues | La courbe cible redescend au moins une fois |
| Aucun doublon | Aucun morceau n'apparaît deux fois dans un set |
| Variation | Deux générations sur la même requête diffèrent |
| Graine fixée | Deux générations avec la même graine sont identiques |
| Normalisation Camelot | `Am`, `8A`, `1m` et une valeur vide donnent le résultat attendu |
| Pénalité harmonique | Chaque ligne du tableau §7 |
| Parsing My Tags | Extraction sur un extrait réel de l'export, commentaire libre compris |
| Mood multiple / absent | Morceau exclu et signalé |
| Export | Le XML produit est bien formé et chaque `TRACK Key` existe dans `COLLECTION` |

L'interface web n'est pas testée automatiquement.

## 13. Ordre de construction

1. Vérifier le format des My Tags sur un export XML réel (bloquant).
2. `model.py` et `config.py`.
3. `rekordbox/reader.py` — parsing, avec fixture tirée de l'export réel.
4. `engine/harmony.py` — normalisation Camelot et pénalité.
5. `engine/curves.py` — types de courbe et profils.
6. `engine/filtering.py` et `engine/sequencing.py`.
7. `rekordbox/writer.py` — export XML.
8. `web/` — API et page unique.
9. Courbe BPM en SVG.

Les étapes 2 à 7 constituent un outil complet et testable sans interface ; l'interface
n'ajoute aucune logique musicale.
