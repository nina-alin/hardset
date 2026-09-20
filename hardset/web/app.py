"""API locale et service de la page unique.

Cette couche n'ajoute aucune logique musicale : elle traduit des requêtes HTTP en
appels au moteur, et sérialise le résultat. Le set courant vit dans le navigateur ;
le serveur ne garde en mémoire que les collections lues.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from urllib.parse import quote

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from hardset.config import Config
from hardset.engine.curves import build_targets
from hardset.engine.sequencing import (
    SequencingError,
    generate,
    replace_at,
    shortage_warnings,
)
from hardset.model import MOOD_MAX, MOOD_MIN, GeneratedSet, SetRequest, Track
from hardset.rekordbox.reader import Collection, CollectionError, read_collection
from hardset.rekordbox.writer import build_playlist_xml, default_playlist_name, slug

STATIC = Path(__file__).parent / "static"


class CollectionPayload(BaseModel):
    path: str


class SetRequestPayload(CollectionPayload):
    genres: list[str] = Field(default_factory=list)
    moods: list[int] = Field(default_factory=list)
    bpm_min: float
    bpm_max: float
    profile: str
    duration_min: int
    # Défaut de schéma, pas une valeur de configuration : la valeur réellement
    # utilisée par le formulaire vient de `/api/config`, elle-même lue dans
    # `config.seconds_per_track` (point tranché de la tâche 10).
    seconds_per_track: int = 120

    def to_request(self) -> SetRequest:
        """Traduit le payload en `SetRequest`, après validation.

        Le moteur ne valide pas ces règles — ce n'est pas son travail — mais une
        requête hors de l'échelle de mood, à plage de BPM inversée, ou à durée ou
        `seconds_per_track` nul ou négatif ne doit jamais l'atteindre : elle
        produirait un set vide indistinguable d'une vraie pénurie.
        """
        for mood in self.moods:
            if not MOOD_MIN <= mood <= MOOD_MAX:
                raise HTTPException(
                    status_code=400,
                    detail=f"mood {mood} hors de l'échelle [{MOOD_MIN}, {MOOD_MAX}]",
                )
        if self.bpm_min > self.bpm_max:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"bpm_min ({self.bpm_min}) ne peut pas être supérieur à "
                    f"bpm_max ({self.bpm_max})"
                ),
            )
        if self.duration_min <= 0:
            raise HTTPException(
                status_code=400, detail="la durée du set doit être strictement positive"
            )
        if self.seconds_per_track <= 0:
            raise HTTPException(
                status_code=400, detail="seconds_per_track doit être strictement positif"
            )
        return SetRequest(
            genres=frozenset(self.genres),
            moods=frozenset(self.moods),
            bpm_min=self.bpm_min,
            bpm_max=self.bpm_max,
            profile=self.profile,
            duration_min=self.duration_min,
            seconds_per_track=self.seconds_per_track,
        )


class ReplacePayload(SetRequestPayload):
    track_ids: list[str]
    position: int


class ExportPayload(CollectionPayload):
    track_ids: list[str]
    playlist_name: str


def _track_payload(track: Track) -> dict:
    return {
        "id": track.id,
        "artist": track.artist,
        "title": track.title,
        "bpm": track.bpm,
        "camelot": track.camelot,
        "mood": track.mood,
        "genres": list(track.genres),
    }


def _set_payload(generated: GeneratedSet, collection: Collection, request: SetRequest) -> dict:
    aujourdhui = date.today()
    return {
        "tracks": [_track_payload(t) for t in generated.tracks],
        "targets": [
            {"position": c.position, "bpm": c.bpm, "mood": c.mood} for c in generated.targets
        ],
        "warnings": [
            {"code": w.code.value, "message": w.message, "track_ids": list(w.track_ids)}
            for w in (*collection.warnings, *generated.warnings)
        ],
        "playlist_name": default_playlist_name(request, aujourdhui),
        "date": aujourdhui.isoformat(),
    }


def _content_disposition(nom: str) -> str:
    """En-tête de téléchargement pour un nom de playlist quelconque.

    Starlette encode les en-têtes en latin-1 : interpoler le nom saisi tel quel
    faisait échouer la route sur « cœur » ou « 100 € », et un saut de ligne y
    serait refusé par un vrai serveur HTTP. On annonce donc deux noms : un
    `filename` ASCII assaini (`slug`), compris de tous les clients, et un
    `filename*` en UTF-8 percent-encodé (RFC 5987) qui porte le nom complet.
    Le nom de fichier réellement enregistré vient de l'attribut `download` du
    lien, côté page : cet en-tête n'est qu'un filet de sécurité.
    """
    ascii_nom = slug(nom) or "set"
    return (
        f'attachment; filename="{ascii_nom}.xml"; '
        f"filename*=UTF-8''{quote(f'{nom}.xml', safe='')}"
    )


def create_app(config: Config) -> FastAPI:
    app = FastAPI(title="hardset", docs_url=None, redoc_url=None)

    # Collections lues, par chemin résolu et date de modification : rouvrir un gros
    # export à chaque clic serait inutilement lent, et le relire dès qu'il change
    # évite de servir des données périmées.
    cache: dict[tuple[str, float], Collection] = {}

    def charger(chemin_brut: str) -> Collection:
        try:
            chemin = Path(chemin_brut).expanduser()
            cle = (str(chemin.resolve()), chemin.stat().st_mtime)
        except PermissionError as exc:
            # Avant `OSError` : un fichier existant mais inaccessible (ou logé
            # dans un répertoire non traversable) n'est pas un fichier absent.
            # Le lecteur fait déjà cette distinction ; la route doit la faire
            # aussi, sans quoi l'utilisatrice cherche un fichier qui est là.
            raise HTTPException(
                status_code=400, detail=f"impossible de lire {chemin} : {exc}"
            ) from exc
        except OSError as exc:
            # `expanduser()` ne lève jamais d'`OSError` : à ce stade `chemin`
            # est nécessairement défini, seule `resolve()`/`stat()` a échoué.
            raise HTTPException(status_code=400, detail=f"export introuvable : {chemin}") from exc
        except (ValueError, RuntimeError) as exc:
            # Un octet NUL dans le chemin fait lever un `ValueError` natif de
            # `pathlib` (« embedded null byte »), et un `~utilisateur` inconnu
            # fait lever un `RuntimeError` depuis `expanduser()` : ni l'un ni
            # l'autre n'est un `OSError`, mais tous deux doivent produire un
            # 400 explicite plutôt que de remonter bruts jusqu'à Starlette.
            raise HTTPException(status_code=400, detail=f"chemin invalide : {exc}") from exc
        if cle not in cache:
            try:
                cache.clear()   # une seule collection à la fois suffit
                cache[cle] = read_collection(chemin, config)
            except CollectionError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
        return cache[cle]

    def resoudre(collection: Collection, track_ids: list[str]) -> list[Track]:
        par_id = {track.id: track for track in collection.tracks}
        try:
            return [par_id[identifiant] for identifiant in track_ids]
        except KeyError as exc:
            raise HTTPException(
                status_code=400, detail=f"morceau {exc.args[0]} absent de la collection"
            ) from exc

    @app.get("/")
    def page() -> FileResponse:
        return FileResponse(STATIC / "index.html")

    @app.get("/api/config")
    def configuration() -> dict:
        return {
            "profils": [
                {"key": p.key, "label": p.label} for p in config.profils.values()
            ],
            "moods": [
                {"value": i, "label": label} for i, label in enumerate(config.moods, start=1)
            ],
            "collection_xml": config.collection_xml,
            # Point tranché : lu dans la configuration, pas un littéral — la
            # page doit refléter ce que `hardset.yaml` déclare.
            "seconds_per_track": config.seconds_per_track,
        }

    @app.post("/api/collection")
    def collection(payload: CollectionPayload) -> dict:
        lue = charger(payload.path)
        bpm_min, bpm_max = lue.bpm_range
        return {
            "path": payload.path,
            "track_count": len(lue.tracks),
            "genres": list(lue.genres),
            "bpm_min": bpm_min,
            "bpm_max": bpm_max,
            "warnings": [
                {"code": w.code.value, "message": w.message, "track_ids": list(w.track_ids)}
                for w in lue.warnings
            ],
        }

    @app.post("/api/generate")
    def generer(payload: SetRequestPayload) -> dict:
        lue = charger(payload.path)
        requete = payload.to_request()
        try:
            resultat = generate(lue.tracks, requete, config)
        except SequencingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _set_payload(resultat, lue, requete)

    @app.post("/api/replace")
    def remplacer(payload: ReplacePayload) -> dict:
        lue = charger(payload.path)
        requete = payload.to_request()
        tracks = resoudre(lue, payload.track_ids)
        try:
            profil = config.profils[requete.profile]
        except KeyError as exc:
            # Même message que celui du moteur sur `/api/generate` (`_profile`
            # dans `engine/sequencing.py`, interface privée et donc non
            # réutilisable ici) : la liste des profils disponibles est ce qui
            # aide réellement l'utilisatrice à corriger sa requête.
            connus = ", ".join(sorted(config.profils))
            raise HTTPException(
                status_code=400,
                detail=f"profil '{requete.profile}' inexistant (disponibles : {connus})",
            ) from exc

        # Les cibles sont recalculées pour la longueur reçue : après une suppression,
        # la courbe se redistribue sur les positions restantes.
        #
        # La pénurie relevée à la génération est recalculée, et non repartie de
        # zéro : le moteur la préserve délibérément à travers les remplacements,
        # et le set courant reconstruit ici doit la porter comme celui que
        # `generate` avait rendu. Elle ne dépend que de la demande et de la
        # collection, donc `shortage_warnings` la redonne à l'identique.
        courant = GeneratedSet(
            tracks=tracks,
            targets=build_targets(requete, profil, len(tracks)),
            warnings=shortage_warnings(lue.tracks, requete),
        )
        try:
            resultat = replace_at(courant, payload.position, lue.tracks, requete, config)
        except SequencingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _set_payload(resultat, lue, requete)

    @app.post("/api/export")
    def exporter(payload: ExportPayload) -> Response:
        lue = charger(payload.path)
        tracks = resoudre(lue, payload.track_ids)
        nom = payload.playlist_name.strip() or "set"
        return Response(
            content=build_playlist_xml(tracks, nom),
            media_type="application/xml",
            headers={"content-disposition": _content_disposition(nom)},
        )

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app
