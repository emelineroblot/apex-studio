"""**Exécution** — recoupement métier et classification par seuils (§3-J.3, étapes 6 et 7).

C'est ici que la sortie du modèle prend — ou ne prend pas — un sens métier. Deux idées
gouvernent tout le module :

**1. Le rattachement est une jointure, pas une inférence.** Un numéro peint sur une
carrosserie ne veut rien dire dans l'absolu : il ne désigne un pilote, une écurie et donc
un client que rapporté à la **table des engagements du shooting**. Ce recoupement est un
`SELECT … FROM engagement WHERE shooting_id = :s AND car_number = :n`. Confier cette
décision au modèle serait une faute de conception, pas une optimisation.

**2. Les candidats bruts sont persistés, la classification est une projection.** Ce que le
modèle a lu (`raw_text`), ce qu'on en a déduit (`normalized_number`), avec quel score et à
quel endroit de l'image, vit dans `media_ocr_candidate`. Changer un seuil **ne relance
jamais l'inférence** : on re-projette les lignes existantes (`reclassify_ocr`). C'est le
point de design le plus important de J2 — et ce qui rend le critère d'acceptation
« changer les seuils redistribue les cas » quasi instantané sur 8 000 médias.

## Les quatre issues, et pourquoi la quatrième est distincte

| Issue | Condition | Effet |
|---|---|---|
| `auto` | numéro **trouvé** dans les engagements et `score ≥ high` | `media_engagement` (`source='ocr'`), `engagement_attached` |
| `review` | trouvé et `low ≤ score < high` | file de validation humaine, `pending_review` |
| `abstain` | trouvé et `score < low` | **aucun** rattachement, le média reste `shooting_attached` |
| `not_engaged` | numéro **absent** de la table, quel que soit le score | `inconsistent` — signalé, **jamais rattaché de force** |

« Pas sûr » et « sûr mais incohérent » ne sont pas la même chose. Un `not_engaged` n'est
pas un échec du modèle : c'est un signal métier (numéro absent du plateau, engagement
oublié à la saisie, voiture d'une autre course dans le cadre). Il mérite un bac à lui, et
il ne se résout pas en baissant un seuil — d'où sa mise hors de la bande de seuils, comme
le prescrit le plan.

## Ce que la projection ne touche jamais

- Les décisions humaines (`accepted` / `rejected`) : ré-exécuter la projection, changer les
  seuils, relancer l'OCR — rien ne les réécrit. L'arbitrage humain est terminal.
- Les rattachements posés à la main (`media_engagement.source = 'human'`) : seuls les
  rattachements d'origine OCR sont ajoutés ou retirés par ce module.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import ColumnElement, and_, case, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from apex.models.media import Media, MediaEngagement
from apex.models.search import MediaOcrCandidate
from apex.models.shooting import Engagement
from apex.pipeline.ocr.normalize import canonical_number
from apex.services.ocr_settings import OcrSettings

RESOLUTION_AUTO = "auto"
RESOLUTION_REVIEW = "review"
RESOLUTION_ABSTAIN = "abstain"
RESOLUTION_NOT_ENGAGED = "not_engaged"
RESOLUTION_ACCEPTED = "accepted"
RESOLUTION_REJECTED = "rejected"

#: Arbitrages humains — terminaux, jamais réécrits par une projection.
HUMAN_RESOLUTIONS = (RESOLUTION_ACCEPTED, RESOLUTION_REJECTED)
#: Résolutions qui matérialisent un rattachement dans `media_engagement`.
ATTACHING_RESOLUTIONS = (RESOLUTION_AUTO, RESOLUTION_ACCEPTED)
#: Résolutions produites par la machine — celles que les seuils redistribuent.
MACHINE_RESOLUTIONS = (RESOLUTION_AUTO, RESOLUTION_REVIEW, RESOLUTION_ABSTAIN)


def decide(*, matched: bool, score: float, high: float, low: float) -> str:
    """Fonction **pure** : la règle de décision complète du projet, en cinq lignes.

    Testée directement, réutilisée telle quelle par l'évaluation offline — c'est la même
    règle qui tourne en production et qui est mesurée dans `docs/ocr-eval.md`.
    """
    if not matched:
        return RESOLUTION_NOT_ENGAGED
    if score >= high:
        return RESOLUTION_AUTO
    if score >= low:
        return RESOLUTION_REVIEW
    return RESOLUTION_ABSTAIN


@dataclass(slots=True)
class ProjectionResult:
    """Compte rendu d'une projection — remonté tel quel dans `job.result`."""

    media_touched: int = 0
    attached: int = 0
    detached: int = 0
    counts: dict[str, int] = field(default_factory=dict)

    def bump(self, resolution: str) -> None:
        self.counts[resolution] = self.counts.get(resolution, 0) + 1


def load_engagements(session: Session, shooting_ids: set[int]) -> dict[tuple[int, str], Engagement]:
    """La jointure métier, chargée en une requête pour tous les shootings concernés.

    Clé : `(shooting_id, forme canonique du numéro)`. La canonicalisation des deux côtés
    évite qu'un « 07 » lu ne rate un engagement saisi « 7 » (cf. `normalize.canonical_number`).
    Un shooting porte quelques dizaines d'engagements : ce chargement reste négligeable même
    quand `reclassify_ocr` balaie tout le catalogue.
    """
    if not shooting_ids:
        return {}
    rows = session.execute(
        select(Engagement).where(Engagement.shooting_id.in_(shooting_ids))
    ).scalars()
    return {(row.shooting_id, canonical_number(row.car_number)): row for row in rows}


def project_media_batch(
    session: Session,
    media_ids: list[int],
    ocr_settings: OcrSettings,
) -> ProjectionResult:
    """Re-projette les candidats déjà persistés de `media_ids`. **Aucune inférence.**

    Ce module n'importe pas `engine.py` — c'est volontaire et vérifié par un test : la
    re-projection doit être structurellement incapable de réveiller le modèle.

    Ne committe pas (la transaction appartient à l'appelant : handler de job ou routeur).
    """
    result = ProjectionResult()
    if not media_ids:
        return result

    medias = {
        media.id: media
        for media in session.execute(select(Media).where(Media.id.in_(media_ids))).scalars()
    }
    if not medias:
        return result

    candidates_by_media: dict[int, list[MediaOcrCandidate]] = {}
    for candidate in session.execute(
        select(MediaOcrCandidate)
        .where(MediaOcrCandidate.media_id.in_(list(medias)))
        .order_by(MediaOcrCandidate.id)
    ).scalars():
        candidates_by_media.setdefault(candidate.media_id, []).append(candidate)

    links_by_media: dict[int, list[MediaEngagement]] = {}
    for link in session.execute(
        select(MediaEngagement).where(MediaEngagement.media_id.in_(list(medias)))
    ).scalars():
        links_by_media.setdefault(link.media_id, []).append(link)

    engagements = load_engagements(
        session, {m.shooting_id for m in medias.values() if m.shooting_id is not None}
    )

    for media_id, media in medias.items():
        candidates = candidates_by_media.get(media_id, [])
        links = links_by_media.get(media_id, [])
        ocr_links = [link for link in links if link.source == "ocr"]

        # Un média sans aucun candidat et sans rattachement OCR n'a rien à projeter :
        # on ne touche pas à son `attachment_status`, qui appartient alors entièrement au
        # rattachement temporel (`pipeline/attach_time.py`) ou à une action humaine.
        if not candidates and not ocr_links:
            continue
        # Un média en quarantaine n'a pas de dérivé fiable : hors sujet ici, jamais muté.
        if media.ingest_status == "quarantined":
            continue

        result.media_touched += 1
        _resolve_candidates(media, candidates, engagements, ocr_settings, result)
        attached, detached, links_after = _materialise_links(session, media, candidates, links)
        result.attached += attached
        result.detached += detached
        _recompute_attachment_status(media, candidates, links_after=links_after)

    session.flush()
    return result


def project_media(session: Session, media: Media, ocr_settings: OcrSettings) -> ProjectionResult:
    """Projection d'un seul média — enveloppe de `project_media_batch`."""
    return project_media_batch(session, [media.id], ocr_settings)


def reconcile_unlinked_attachment_status(session: Session, media_ids: list[int]) -> int:
    """Filet de sécurité (revue J2, 🟠 n°2) : remet à plat `attachment_status` pour tout
    média de `media_ids` encore marqué `engagement_attached` alors qu'il ne porte plus
    **aucun** `media_engagement` — cas qu'`_recompute_attachment_status` ne voit jamais
    puisqu'il tourne à l'intérieur de `project_media_batch`, lequel ignore tout média sans
    candidat OCR ni lien `source='ocr'` (§ sa docstring). C'est exactement le cas d'un
    rattachement **manuel** (`source='human'`, aucun candidat) dont l'engagement source
    vient d'être supprimé (`DELETE /engagements/{id}`, cascade sur `media_engagement`) :
    sans ce filet, le média reste indéfiniment `engagement_attached` avec zéro rattachement,
    et `/media` comme `/search` continuent de l'afficher rattaché. Renvoie le nombre de
    médias corrigés.
    """
    ids = list({int(i) for i in media_ids})
    if not ids:
        return 0
    linked_ids = {
        int(row)
        for row in session.execute(
            select(MediaEngagement.media_id).where(MediaEngagement.media_id.in_(ids)).distinct()
        ).scalars()
    }
    orphaned_ids = [i for i in ids if i not in linked_ids]
    if not orphaned_ids:
        return 0
    medias = (
        session.execute(
            select(Media).where(
                Media.id.in_(orphaned_ids), Media.attachment_status == "engagement_attached"
            )
        )
        .scalars()
        .all()
    )
    for media in medias:
        media.attachment_status = (
            "shooting_attached" if media.shooting_id is not None else "unattached"
        )
    return len(medias)


def media_ids_with_reprojectable_candidates(session: Session, shooting_id: int) -> list[int]:
    """Médias d'un shooting portant un candidat OCR encore « machine » (§ `HUMAN_RESOLUTIONS`,
    terminal exclu) — y compris `not_engaged` (numéro absent des engagements au moment de la
    lecture). Utilisé après une mutation du référentiel qui peut changer la réponse à
    « ce numéro est-il engagé ? » (revue J2, 🟠 n°2) : import CSV, création/correction d'un
    engagement. Sans reprojection, un `not_engaged` devenu valide reste bloqué dans le bac
    « incohérences » alors que l'engagement qui le justifierait existe désormais.
    """
    rows = session.execute(
        select(MediaOcrCandidate.media_id)
        .join(Media, Media.id == MediaOcrCandidate.media_id)
        .where(
            Media.shooting_id == shooting_id,
            MediaOcrCandidate.resolution.not_in(HUMAN_RESOLUTIONS),
        )
        .distinct()
    ).scalars()
    return [int(r) for r in rows]


def _resolve_candidates(
    media: Media,
    candidates: list[MediaOcrCandidate],
    engagements: dict[tuple[int, str], Engagement],
    ocr_settings: OcrSettings,
    result: ProjectionResult,
) -> None:
    for candidate in candidates:
        if candidate.resolution in HUMAN_RESOLUTIONS:
            # Arbitrage humain : terminal. On le compte, on n'y touche pas.
            result.bump(candidate.resolution)
            continue

        if media.shooting_id is None or candidate.normalized_number is None:
            # Sans shooting, il n'existe aucune table d'engagements à interroger : on ne
            # peut ni rattacher ni crier à l'incohérence. On s'abstient — c'est le cas d'un
            # média détaché de son shooting après correction d'horloge.
            candidate.resolution = RESOLUTION_ABSTAIN
            candidate.engagement_id = None
            result.bump(RESOLUTION_ABSTAIN)
            continue

        key = (media.shooting_id, canonical_number(candidate.normalized_number))
        engagement = engagements.get(key)
        resolution = decide(
            matched=engagement is not None,
            score=float(candidate.confidence),
            high=ocr_settings.high,
            low=ocr_settings.low,
        )
        candidate.resolution = resolution
        # `engagement_id` est conservé même en `abstain` : c'est la suggestion affichée, et
        # c'est ce qui rend la simulation de redistribution (`PUT /settings/ocr`) exacte en
        # SQL — un candidat machine sans `engagement_id` serait indistinguable d'un
        # `not_engaged` une fois les seuils changés.
        candidate.engagement_id = engagement.id if engagement is not None else None
        result.bump(resolution)


#: Rattachement subsistant après projection, réduit à ce dont dépend `attachment_status` :
#: `(engagement_id, source, un humain est-il intervenu ?)`.
LinkAfter = tuple[int, str, bool]


def _materialise_links(
    session: Session,
    media: Media,
    candidates: list[MediaOcrCandidate],
    links: list[MediaEngagement],
) -> tuple[int, int, list[LinkAfter]]:
    """Aligne `media_engagement` (côté OCR uniquement) sur les résolutions courantes.

    Un média peut porter **plusieurs** rattachements : deux voitures numérotées dans le
    cadre produisent deux candidats, donc deux lignes — la clé primaire composite
    `(media_id, engagement_id)` est faite pour ça.

    Renvoie aussi l'état des rattachements **après** l'opération, sous forme de tuples
    plats : `_recompute_attachment_status` en a besoin, et le relire en base obligerait à
    un `flush()` par média au milieu d'un lot de 8 000.
    """
    desired: dict[int, MediaOcrCandidate] = {}
    for candidate in candidates:
        if candidate.resolution in ATTACHING_RESOLUTIONS and candidate.engagement_id is not None:
            desired[candidate.engagement_id] = candidate

    ocr_links = [link for link in links if link.source == "ocr"]
    kept: list[LinkAfter] = [
        (link.engagement_id, link.source, link.created_by is not None)
        for link in links
        if link.source != "ocr"
    ]

    detached = 0
    surviving_ocr_ids: set[int] = set()
    for link in ocr_links:
        if link.engagement_id in desired:
            surviving_ocr_ids.add(link.engagement_id)
            kept.append((link.engagement_id, "ocr", link.created_by is not None))
            continue
        # Un seuil relevé retire le rattachement automatique qu'il ne justifie plus.
        # Seules les lignes `source='ocr'` sont concernées : un rattachement humain n'est
        # jamais défait par un changement de réglage.
        session.delete(link)
        detached += 1

    attached = 0
    for engagement_id, candidate in desired.items():
        if engagement_id in surviving_ocr_ids:
            continue
        session.execute(
            pg_insert(MediaEngagement)
            .values(
                media_id=media.id,
                engagement_id=engagement_id,
                source="ocr",
                confidence=float(candidate.confidence),
                # Traçabilité : `NULL` = la machine seule ; renseigné = un humain a tranché.
                # C'est cette colonne qui distingue `auto_ocr` de `human` dans le taux de
                # rattachement automatique (`GET /stats/auto-attach-rate`).
                created_by=candidate.resolved_by,
            )
            .on_conflict_do_nothing(index_elements=["media_id", "engagement_id"])
        )
        kept.append((engagement_id, "ocr", candidate.resolved_by is not None))
        attached += 1
    return attached, detached, kept


def _recompute_attachment_status(
    media: Media,
    candidates: list[MediaOcrCandidate],
    *,
    links_after: list[LinkAfter],
) -> None:
    """Ordre de priorité, du plus informatif au plus neutre.

    Un média rattaché **est** rattaché, même s'il porte par ailleurs un second candidat en
    attente d'arbitrage (deux voitures, une reconnue et une douteuse) : la file de
    validation se lit sur les candidats, pas sur cet état-là.
    """
    if links_after:
        media.attachment_status = "engagement_attached"
        human_touch = any(source == "human" or by_human for _, source, by_human in links_after)
        media.attachment_source = "human" if human_touch else "pipeline_ocr"
        return

    resolutions = {candidate.resolution for candidate in candidates}
    if RESOLUTION_REVIEW in resolutions:
        media.attachment_status = "pending_review"
        return
    if RESOLUTION_NOT_ENGAGED in resolutions:
        media.attachment_status = "inconsistent"
        return

    if media.shooting_id is not None:
        media.attachment_status = "shooting_attached"
        # Le média n'est plus rattaché à un engagement : la seule chose qu'on sache encore
        # de lui est **comment il a rejoint son shooting**. On ne réécrit pas un
        # rattachement humain au shooting en « automatique ».
        if media.attachment_source != "human":
            media.attachment_source = "pipeline_time"
        return

    media.attachment_status = "unattached"


# ---------------------------------------------------------------------------------------
# Distribution des candidats — lecture et **simulation**, toutes deux en SQL pur.
#
# La simulation est ce qui permet à `PUT /settings/ocr` de répondre « voilà ce que ces
# seuils donneraient » **avant** d'écrire quoi que ce soit. Elle n'écrit rien, ne relance
# rien, et coûte une agrégation sur `media_ocr_candidate` : c'est la conséquence directe du
# choix de persister les candidats bruts.
# ---------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Distribution:
    """Les quatre bacs. `not_engaged` est hors bande de seuils : il ne bouge jamais."""

    auto: int
    review: int
    abstain: int
    not_engaged: int


def current_distribution(session: Session) -> Distribution:
    """Distribution réellement inscrite en base.

    Les arbitrages humains sont comptés dans le bac où ils aboutissent : `accepted` avec
    les rattachements automatiques (la photo est rattachée), `rejected` avec les
    abstentions (elle ne l'est pas). L'écran de réglages compare cette distribution à la
    simulation ; les deux doivent donc parler de la même chose.
    """
    rows: dict[str, int] = {
        str(resolution): int(count)
        for resolution, count in session.execute(
            select(MediaOcrCandidate.resolution, func.count())
            .select_from(MediaOcrCandidate)
            .group_by(MediaOcrCandidate.resolution)
        ).all()
    }
    return Distribution(
        auto=rows.get(RESOLUTION_AUTO, 0) + rows.get(RESOLUTION_ACCEPTED, 0),
        review=rows.get(RESOLUTION_REVIEW, 0),
        abstain=rows.get(RESOLUTION_ABSTAIN, 0) + rows.get(RESOLUTION_REJECTED, 0),
        not_engaged=rows.get(RESOLUTION_NOT_ENGAGED, 0),
    )


#: Portée d'un candidat réellement **projetable** — ce que `_resolve_candidates` touche
#: quand `project_media_batch` tourne (revue J2, 🟠 n°5). Un candidat en dehors de cette
#: portée garde sa résolution courante, quel que soit le seuil simulé :
#: - `HUMAN_RESOLUTIONS` (`accepted`/`rejected`) : terminal, jamais réécrit.
#: - un média `ingest_status == 'quarantined'` : `project_media_batch` l'ignore explicitement
#:   (« un média en quarantaine n'a pas de dérivé fiable, jamais muté ») — la simulation
#:   l'incluait pourtant dans ses calculs, un premier écart trouvé en écrivant ce correctif.
def _candidate_scope(*, media_ingest_status: Any, resolution: Any) -> ColumnElement[bool]:
    return and_(resolution.not_in(HUMAN_RESOLUTIONS), media_ingest_status != "quarantined")


def simulate_distribution(session: Session, *, high: float, low: float) -> Distribution:
    """Ce que donneraient ces seuils, **sans rien écrire ni ré-inférer**.

    Revue J2 (🟠 n°5) : l'ancienne version excluait purement et simplement les candidats
    d'un média sans shooting (`Media.shooting_id IS NULL`) de la simulation, alors que
    `_resolve_candidates` les force en **abstention** (jamais silencieusement ignorés).
    Scénario reproduit : un recalage d'horloge détache 400 photos de leur shooting —
    `GET /settings/ocr` (état réel, `current_distribution`) affiche `abstain: 411`,
    l'aperçu de `PUT /settings/ocr` n'en comptait que `11`, et la redistribution réelle qui
    suit redonne `411`. La simulation était vendue comme exacte, pas indicative.

    Une seule expression `CASE`, transcription directe de `_resolve_candidates` (portée
    `_candidate_scope` ci-dessus, puis `decide()`) plutôt que quatre `FILTER` disjoints
    reconstruits à la main — la même classe d'écart (une seconde formulation d'une règle déjà
    écrite ailleurs) que celle refermée pour le cloisonnement de rôle (🟠 n°4) : ici la
    correction porte sur la portée « candidats projetables », partagée par la lecture
    (`current_distribution`, via le passage direct de la résolution courante) et
    l'écriture réelle.

    `engagement_id` (et non la résolution courante) dit si le numéro a été retrouvé au
    plateau : c'est un **fait** posé par la projection précédente (§`_resolve_candidates`),
    indépendant des seuils, donc stable sous simulation — la résolution, elle, est justement
    ce que la simulation fait varier, elle ne peut pas servir d'entrée.

    Précondition, garantie par construction : tout candidat persisté a déjà été projeté au
    moins une fois — `handle_ocr_media` insère et projette dans la **même** transaction,
    il n'existe jamais de candidat « brut, non résolu » visible d'une autre transaction.
    """
    resolution = MediaOcrCandidate.resolution
    confidence = MediaOcrCandidate.confidence
    scope = _candidate_scope(media_ingest_status=Media.ingest_status, resolution=resolution)
    bucket = case(
        # Hors portée : la résolution courante ne bouge pas, quel que soit le seuil.
        (~scope, resolution),
        # Sans shooting, aucune table d'engagements à interroger — abstention
        # inconditionnelle, jamais un score qui déciderait à sa place.
        (Media.shooting_id.is_(None), RESOLUTION_ABSTAIN),
        # Hors bande de seuils par construction : aucun réglage ne rend engagée une voiture
        # qui n'est pas au départ.
        (MediaOcrCandidate.engagement_id.is_(None), RESOLUTION_NOT_ENGAGED),
        (confidence >= high, RESOLUTION_AUTO),
        (confidence >= low, RESOLUTION_REVIEW),
        else_=RESOLUTION_ABSTAIN,
    )
    rows = session.execute(
        select(bucket, func.count())
        .select_from(MediaOcrCandidate)
        .join(Media, Media.id == MediaOcrCandidate.media_id)
        .group_by(bucket)
    ).all()
    counts = {str(row[0]): int(row[1]) for row in rows}
    return Distribution(
        auto=counts.get(RESOLUTION_AUTO, 0) + counts.get(RESOLUTION_ACCEPTED, 0),
        review=counts.get(RESOLUTION_REVIEW, 0),
        abstain=counts.get(RESOLUTION_ABSTAIN, 0) + counts.get(RESOLUTION_REJECTED, 0),
        not_engaged=counts.get(RESOLUTION_NOT_ENGAGED, 0),
    )
