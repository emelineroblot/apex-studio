"""Projection de recherche `media_search` (§3-K.1 du plan, Décision K).

**Une seule table, zéro jointure côté lecture.** `media_search` porte les colonnes
scalaires de facette (`shooting_id`, `client_id`, `circuit_id`, `camera_id`, `lens_model`,
`attachment_status`, `iso`, `focal_length`) et des tableaux dénormalisés
(`team_ids`, `driver_ids`, `car_numbers`, issus de la relation N:N `media_engagement`) plus
un `tsvector` pondéré. Elle est reconstruite par le pipeline, **pas** par trigger — la mise
à jour reste explicite, donc lisible et débogable (§3-K.1, option retenue).

**Une seule fonction, deux usages.** `project_media_search()` est un unique `INSERT …
SELECT … ON CONFLICT (media_id) DO UPDATE`, exécuté soit sur un sous-ensemble de médias
(réindexation incrémentale — ingestion, rattachement, arbitrage humain, recalage
d'horloge), soit sur la table entière (`media_ids=None` — `apex.cli reindex`, jeu de
démo). C'est la **même** requête dans les deux cas : le jeu de démo (~8000 lignes) n'a pas
de chemin de projection séparé, ce qui garantit qu'il ne peut pas diverger de la
projection incrémentale (§ Décision N.1, « un unique `INSERT INTO media_search SELECT …` »).

**Une projection périmée est un média introuvable.** Point de sortie signalé par l'agent
OCR (§ `.agent-team/implementation.md`, « J2 — OCR ») : `reindex_media` n'était câblé nulle
part. Ce module est appelé, synchrone et dans la **même transaction**, à chaque endroit où
`attachment_status`, le rattachement (`media_engagement`), la série
(`is_series_representative`) ou l'identité du shooting/boîtier d'un média changent —
ingestion (`pipeline/ingest.py`), OCR (`queue/handlers/ocr_media.py`), reclassement
(`queue/handlers/reclassify_ocr.py`), arbitrage humain (`routers/review.py`), rattachement/
retrait manuel (`routers/media.py`) et recalage d'horloge
(`queue/handlers/reattach_camera.py`). Le job `reindex_media` (`queue/handlers/
reindex_media.py`) n'est qu'un point d'entrée asynchrone supplémentaire pour ces mêmes
appels — jamais le seul chemin.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import select, text
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session

from apex.models.media import Media

# Config de recherche plein texte (§3-K.3) : légendes/mots-clés pondérés `A`, le reste `B`.
_FTS_CONFIG = "french"

# `INSERT … SELECT … ON CONFLICT DO UPDATE` — une seule requête, portée par le paramètre
# `media_ids` (`NULL` => toute la table `media`, réindexation complète). `LEFT JOIN LATERAL`
# agrège les engagements du média en une seule passe (équipes/pilotes/numéros + leurs
# libellés pour le `tsvector`) sans repasser par une sous-requête corrélée par colonne.
#
# **Piège vérifié** : le motif de reconnaissance des bind params de `sqlalchemy.text()`
# scanne la chaîne SQL **brute**, commentaires `--` inclus, et exclut tout `:identifiant`
# immédiatement suivi d'un second `:` (pour ne pas capturer l'opérateur de cast Postgres
# `::` collé à une colonne). D'où deux règles pour ce module : (1) un espace avant tout
# `::cast` sur un paramètre nommé (`:media_ids ::bigint[]`, jamais collé) ; (2) aucune
# mention de la forme `:mot` dans un commentaire SQL à l'intérieur de `text(...)` — même en
# prose, SQLAlchemy la lirait comme un paramètre requis et ferait échouer l'exécution
# (`A value is required for bind parameter`), reproduit en conditions réelles avant ce
# commentaire-ci n'existe sous sa forme actuelle.
_PROJECT_SQL = text(
    """
    INSERT INTO media_search (
        media_id, shooting_id, uploaded_by, client_id, circuit_id, camera_id, lens_model,
        attachment_status, ingest_status, is_simulated, series_id, shot_at, iso,
        focal_length, team_ids, driver_ids, car_numbers,
        is_series_representative, duplicate_of_media_id, search_vector, updated_at
    )
    SELECT
        m.id,
        m.shooting_id,
        m.uploaded_by,
        s.client_id,
        s.circuit_id,
        m.camera_id,
        m.lens_model,
        m.attachment_status,
        m.ingest_status,
        m.is_simulated,
        m.series_id,
        m.shot_at,
        m.iso,
        m.focal_length,
        agg.team_ids,
        agg.driver_ids,
        agg.car_numbers,
        m.is_series_representative,
        m.duplicate_of_media_id,
        -- Chaque terme est déjà un `tsvector` pondéré (`setweight`) ; `||` concatène des
        -- `tsvector`, pas du texte — un `to_tsvector()` englobant serait une erreur de type
        -- (`to_tsvector(text, tsvector)` n'existe pas), reproduit en conditions réelles.
        setweight(to_tsvector(:fts_config, coalesce(m.caption, '')), 'A')
        || setweight(
            to_tsvector(:fts_config, coalesce(array_to_string(m.keywords, ' '), '')), 'A'
        )
        || setweight(to_tsvector(:fts_config, coalesce(agg.driver_names, '')), 'B')
        || setweight(to_tsvector(:fts_config, coalesce(agg.team_names, '')), 'B')
        || setweight(to_tsvector(:fts_config, coalesce(agg.car_numbers_text, '')), 'B')
        || setweight(to_tsvector(:fts_config, coalesce(c.name, '')), 'B'),
        now()
    FROM media m
    LEFT JOIN shooting s ON s.id = m.shooting_id
    LEFT JOIN circuit c ON c.id = s.circuit_id
    LEFT JOIN LATERAL (
        SELECT
            array_agg(DISTINCT e.team_id) FILTER (WHERE e.team_id IS NOT NULL) AS team_ids,
            array_agg(DISTINCT e.driver_id) FILTER (WHERE e.driver_id IS NOT NULL) AS driver_ids,
            array_agg(DISTINCT e.car_number) AS car_numbers,
            string_agg(DISTINCT d.full_name, ' ') AS driver_names,
            string_agg(DISTINCT t.name, ' ') AS team_names,
            string_agg(DISTINCT e.car_number, ' ') AS car_numbers_text
        FROM media_engagement me
        JOIN engagement e ON e.id = me.engagement_id
        LEFT JOIN driver d ON d.id = e.driver_id
        LEFT JOIN team t ON t.id = e.team_id
        WHERE me.media_id = m.id
    ) agg ON true
    WHERE (:media_ids ::bigint[] IS NULL OR m.id = ANY(:media_ids ::bigint[]))
    ON CONFLICT (media_id) DO UPDATE SET
        shooting_id = EXCLUDED.shooting_id,
        uploaded_by = EXCLUDED.uploaded_by,
        client_id = EXCLUDED.client_id,
        circuit_id = EXCLUDED.circuit_id,
        camera_id = EXCLUDED.camera_id,
        lens_model = EXCLUDED.lens_model,
        attachment_status = EXCLUDED.attachment_status,
        ingest_status = EXCLUDED.ingest_status,
        is_simulated = EXCLUDED.is_simulated,
        series_id = EXCLUDED.series_id,
        shot_at = EXCLUDED.shot_at,
        iso = EXCLUDED.iso,
        focal_length = EXCLUDED.focal_length,
        team_ids = EXCLUDED.team_ids,
        driver_ids = EXCLUDED.driver_ids,
        car_numbers = EXCLUDED.car_numbers,
        is_series_representative = EXCLUDED.is_series_representative,
        duplicate_of_media_id = EXCLUDED.duplicate_of_media_id,
        search_vector = EXCLUDED.search_vector,
        updated_at = EXCLUDED.updated_at
    """
)


def project_media_search(session: Session, media_ids: Sequence[int] | None = None) -> int:
    """(Ré)écrit la ligne `media_search` de `media_ids` (`None` => table entière).

    Ne committe pas : la transaction appartient à l'appelant, comme partout ailleurs dans
    le pipeline (§3-E.4.2). Renvoie le nombre de lignes touchées.
    """
    ids = list(media_ids) if media_ids is not None else None
    if ids is not None and not ids:
        return 0
    result = cast(
        "CursorResult[Any]",
        session.execute(_PROJECT_SQL, {"media_ids": ids, "fts_config": _FTS_CONFIG}),
    )
    session.flush()
    return int(result.rowcount or 0)


def project_media(session: Session, media_id: int) -> None:
    """Enveloppe à un seul média — lisibilité aux points d'appel synchrones."""
    project_media_search(session, [media_id])


def project_media_search_for_shooting(session: Session, shooting_id: int) -> int:
    """Réindexe **tous** les médias d'un shooting.

    Nécessaire après `pipeline/series.py::regroup_bursts_for_shooting` : le regroupement
    des rafales efface et reconstruit les séries de **tout** le shooting (pas seulement le
    sous-ensemble d'un lot ou d'un boîtier), donc `is_series_representative` peut avoir
    changé pour des médias hors du déclencheur immédiat (`finalize_batch`,
    `reattach_camera`).
    """
    ids = [
        int(mid)
        for mid in session.execute(
            select(Media.id).where(Media.shooting_id == shooting_id)
        ).scalars()
    ]
    return project_media_search(session, ids)
