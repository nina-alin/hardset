# Son de départ et son de fin choisis

Date : 2026-09-20
Statut : design validé, prêt pour planification

Ce document complète
`2026-09-18-generateur-de-sets-rekordbox-design.md`, qu'il ne remplace pas :
tout ce qu'il ne mentionne pas reste tel qu'il y est décrit.

## 1. Objectif

Permettre de choisir, avant la génération, le morceau qui ouvre le set et celui
qui le ferme. Les deux choix sont **facultatifs** et indépendants : ni l'un, ni
l'autre, ou les deux.

La plage de BPM demandée s'accorde alors automatiquement au tempo des morceaux
choisis — le son de départ impose le BPM min, le son de fin impose le BPM max —
sans que l'utilisatrice ait à recopier les valeurs à la main.

## 2. Périmètre

Dans le périmètre :

- recherche d'un morceau dans la collection chargée, par artiste ou par titre ;
- épinglage d'un morceau en première et/ou en dernière position du set ;
- dérivation automatique de `bpm_min` / `bpm_max` depuis les morceaux épinglés ;
- avertissements quand un morceau épinglé sort des critères demandés, ou quand
  le set est trop court pour porter les deux.

Hors périmètre, décidé explicitement :

- **accord du mood** aux morceaux choisis : seul le BPM s'accorde. La demande ne
  portait que sur le tempo, et l'échelle de mood n'a pas de raison de se
  contracter parce qu'un opener est calme ;
- **anticipation harmonique** : l'algorithme reste glouton et ne regarde jamais
  en avant. L'avant-dernier morceau est donc choisi sans tenir compte de la
  tonalité du son de fin épinglé ;
- **set descendant** (son de fin plus lent que le son de départ) : refusé par un
  message explicite. Le supporter demanderait de séparer les bornes du vivier
  des extrémités de la courbe, aujourd'hui confondues dans `bpm_min` /
  `bpm_max` ; c'est un autre chantier ;
- **verrouillage des lignes épinglées** dans la tracklist : l'épinglage est une
  contrainte de génération, pas un verrou d'édition (voir § 6).

## 3. Décisions actées

| Sujet | Décision | Raison |
|---|---|---|
| Choix du morceau | Champ de recherche, 20 résultats max | Tient à 706 morceaux comme à 5 000, là où un `<select>` complet est illisible dès quelques centaines |
| Choix contre filtres | Le choix gagne, un avertissement le signale | Un choix explicite passe avant un critère coché ; refuser obligerait à élargir les filtres pour tout le set |
| Propriétaire de l'accord des BPM | Le serveur | Même raison que pour la courbe cible (commit `44f254f`) : c'est de la logique musicale, elle n'a qu'un propriétaire |
| Rôle du champ BPM dans la page | Reflet verrouillé | La page affiche la valeur imposée et empêche de la modifier ; le serveur ne lit jamais ce qu'elle a envoyé |
| Son de fin plus lent que le départ | Refus, message nommant les deux tempos | Voir § 2 |

## 4. Architecture

Un module ajouté, trois modifiés. La séparation des couches est inchangée, et
`hardset/engine/` reste du Python pur — `test_architecture.py` continue de le
garder.

### 4.1 `hardset/engine/pinning.py` (nouveau)

```python
@dataclass(frozen=True)
class Pins:
    start: Track | None = None
    end: Track | None = None

class PinningError(Exception):
    """Choix d'épinglage inexploitable."""

def resolve(tracks: Iterable[Track], request: SetRequest) -> tuple[SetRequest, Pins]:
    """Résout les morceaux épinglés et accorde la plage de BPM à leur tempo."""
```

`resolve` rend une demande dont `bpm_min` vaut le BPM du son de départ quand il
y en a un, et `bpm_max` celui du son de fin quand il y en a un. Les bornes sans
morceau choisi sont laissées telles quelles.

Elle est **idempotente** : la réappliquer à son propre résultat ne change rien,
puisque la valeur dérivée est déjà celle du morceau épinglé. C'est ce qui
autorise `generate`, `shortage_warnings` et la couche web à l'appeler chacune
pour son compte, sans se coordonner et sans risque de dérive.

Sans aucun id épinglé, elle rend la demande inchangée et n'a pas besoin de
parcourir `tracks`.

**Conséquence assumée.** `bpm_min` / `bpm_max` sont à la fois les extrémités de
la courbe et les bornes du vivier (`engine/filtering.eligible`). Accorder la
borne au morceau épinglé la déplace donc aussi pour **tout le reste du set** :
un son de départ à 182 BPM écarte du vivier tout ce qui est plus lent. C'est
voulu — un set qui ouvre à 182 n'a rien à faire à 150 ensuite — mais c'est un
effet de bord réel, et c'est la même confusion des deux rôles qui interdit les
sets descendants (§ 2).

Elle lève `PinningError` dans trois cas, et trois seulement :

| Cas | Message |
|---|---|
| Un id absent de la collection | `morceau <id> absent de la collection` |
| Le même morceau des deux côtés | `le même morceau ne peut pas être à la fois le son de départ et le son de fin` |
| Plage dérivée vide | `le son de fin (<x> BPM) est plus lent que le son de départ (<y> BPM)`, ou la variante qui nomme la borne saisie quand c'est elle qui ferme la plage |

Le troisième cas couvre deux situations de même nature : deux morceaux épinglés
en ordre inverse, et un seul morceau épinglé qui sort de la borne restée
saisie (un départ à 190 alors que le BPM max vaut 180). Dans les deux cas la
plage dérivée est vide et aucun set n'est possible ; seul le message diffère,
pour nommer ce qu'il faut corriger.

### 4.2 `hardset/model.py`

`SetRequest` gagne deux champs, `None` par défaut :

```python
start_track_id: str | None = None
end_track_id: str | None = None
```

Le défaut préserve tous les appels existants, tests compris, et le CLI qui ne
construit pas de `SetRequest`.

### 4.3 `hardset/engine/sequencing.py`

`generate` appelle `resolve` en premier, puis travaille sur la demande accordée.

1. le vivier est le vivier éligible habituel, **privé des morceaux épinglés**,
   qu'ils en fassent partie ou non — sans quoi un épinglé éligible pourrait être
   placé deux fois ;
2. le nombre de morceaux disponibles est `len(vivier) + nombre d'épinglés
   effectivement plaçables` : les épinglés comptent dans la longueur du set bien
   qu'ils ne viennent pas du vivier. `shortage_warnings` passe par le même
   calcul, sinon les deux divergent d'au plus 2 et l'avertissement de pénurie
   devient faux après un remplacement ;
3. les cibles sont construites comme aujourd'hui, pour la longueur retenue ;
4. la position 0 reçoit le son de départ et la **dernière position du set
   réellement produit** reçoit le son de fin — celle du set raccourci quand les
   morceaux manquent, et non celle du set demandé. Les autres positions sont
   remplies par le tirage habituel, de gauche à droite. Le voisin précédent
   d'une position est le morceau réellement placé avant elle, morceau épinglé
   compris.

   Quand le set ne compte qu'une position, elle reçoit le son de départ s'il y
   en a un, sinon le son de fin (§ 5).

Un morceau épinglé n'est **pas** noté par `cost` : il est placé, pas choisi. Sa
position peut donc s'écarter de la cible, et la courbe affichée le montrera —
c'est honnête, c'est une contrainte imposée, pas un échec de sélection.

`replace_at` appelle `resolve` lui aussi, pour que les cibles qu'il utilise
soient celles de la demande accordée. Il n'a pas à protéger les positions
épinglées : les morceaux en place sont déjà exclus du vivier de remplacement par
`deja_places`.

### 4.4 `hardset/web/app.py`

**Route ajoutée — `POST /api/tracks`**

```
{"path": "...", "q": "burn", "limit": 20}
→ {"tracks": [ ... ], "truncated": true}
```

- la recherche est normalisée par `normalize_tag` (minuscules, sans accents) et
  porte sur `"<artiste> <titre>"` ;
- **tous** les mots de `q` doivent y figurer, dans n'importe quel ordre : `dj burn`
  trouve `DJ Something — Burn It Down` ;
- `q` vide rend une liste vide — la page invite alors à taper ;
- `limit` vaut 20 par défaut, 100 au maximum ; `truncated` dit qu'il y avait
  davantage de résultats, pour que la page puisse le signaler ;
- les morceaux sont sérialisés par `_track_payload`, déjà en place ;
- **aucun filtre n'est appliqué** : un morceau sans mood, hors plage de BPM ou
  hors genres cochés doit pouvoir être épinglé (§ 3).

**Routes modifiées**

`SetRequestPayload` transporte `start_track_id` et `end_track_id`, tous deux
facultatifs, et les recopie dans la `SetRequest` sans les valider : c'est
`resolve` qui valide, et `PinningError` est traduite en HTTP 400 comme
`SequencingError` l'est déjà.

`/api/targets` ne charge la collection **que** si un id épinglé est présent :
sans épinglage elle garde la propriété que sa docstring défend — les cibles ne
dépendent pas de la collection. Avec épinglage elle en a besoin pour connaître
le tempo des morceaux choisis, et le cache rend ce chargement gratuit en
pratique. Son plafond `TARGETS_COUNT_MAX` reste justifié tel quel, `count` ne
dépendant toujours pas de la taille de la collection.

## 5. Nouveaux avertissements

Deux codes ajoutés à `WarningCode`, affichés par le même bandeau que les autres,
sans interrompre la génération :

| Code | Quand | Message |
|---|---|---|
| `pin_off_filters` | Un morceau épinglé ne passerait pas `eligible` (mood non coché, genre non coché, ou aucun mood tagué) | `« <artiste — titre> » est placé en première position bien qu'il ne corresponde pas aux critères demandés` (et sa variante « dernière ») |
| `pin_dropped` | Le set ne compte qu'une position et deux morceaux sont choisis | `le son de fin n'a pas pu être placé : le set ne compte qu'une position` |

La règle du set d'une seule position : **le départ l'emporte**. Le choix est
arbitraire mais fixé et documenté ; il vaut mieux qu'un échec, ce cas
n'arrivant que par accident (durée d'une minute pour deux minutes par morceau).

## 6. Interface

Un `<fieldset>` pleine largeur sous les trois colonnes existantes :
**« Début et fin du set (facultatif) »**, deux champs de recherche côte à côte.

Cycle d'un champ :

1. **avant chargement d'une collection** — le champ est inactif et porte la même
   invite que le bloc des genres ;
2. **saisie** — chaque frappe déclenche, après une temporisation courte, un
   appel à `/api/tracks`. Les résultats sont des `<button>` dans une liste :
   Tab et Entrée les atteignent nativement, sans construction ARIA maison ;
3. **choix** — le champ est remplacé par une étiquette
   `📌 Artiste — Titre · 182 BPM ✕`. Au même instant le champ **BPM min** (ou
   **BPM max**) prend la valeur, devient non modifiable et affiche
   `imposé par le son de départ` ;
4. **retrait** — le ✕ rend la main au champ BPM et lui rend la borne de la
   collection, celle que le chargement y avait mise.

Dans la tracklist, une ligne dont l'id est celui d'un morceau épinglé porte un
📌. Le repère suit le morceau s'il est déplacé, puisqu'il est posé par
comparaison d'id et non par position. Les boutons ↑ ↓ ⟳ ✕ restent actifs sur
ces lignes : le set reste éditable à la main comme aujourd'hui.

Charger une autre collection efface les deux choix, comme il efface déjà le set
affiché : ils ne lui appartiennent plus.

## 7. Tests

| Fichier | Ce qu'il couvre |
|---|---|
| `tests/test_pinning.py` (nouveau) | `resolve` : dérivation des deux bornes, chacune séparément, idempotence, et les trois `PinningError` |
| `tests/test_sequencing.py` | Placement en première et dernière position, exclusion du vivier, décompte de pénurie incluant les épinglés, les deux avertissements, set d'une seule position, vivier plus court que la durée demandée |
| `tests/test_api.py` | `/api/tracks` (recherche multi-mots, `q` vide, plafond de `limit`, `truncated`, absence de filtrage) ; dérivation des BPM par `/api/generate`, `/api/replace` et `/api/targets` ; les `PinningError` traduites en 400 |
| `tests/test_bout_en_bout.py` | Une génération épinglée des deux côtés sur la fixture riche, jusqu'au XML exporté |

Le JavaScript n'a pas de tests dans ce dépôt (hors périmètre acté du design
initial) : la page est vérifiée à la main dans le navigateur avant livraison.

## 8. Ce que ce document n'atteste pas

Comme tout le reste du dépôt : **aucun fichier produit par cet outil n'a jamais
été réimporté dans Rekordbox.** Épingler un son de départ ne change rien à ce
point, qui reste entièrement à vérifier devant un vrai Rekordbox.
