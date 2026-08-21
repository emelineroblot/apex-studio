"""Accord `GET /media` ↔ `GET /search` sur ce qui est visible (intégration live J2, défaut
signalé : `/search` masquait structurellement le bac « à rattacher » et sous-comptait les
médias non représentatifs de leur série — §3-G, réimplémenté indépendamment dans
`services/facets.py::_base_predicates` sans reprendre la clause de défense « média sans
shooting » ajoutée en clôture de J1 dans `routers/media.py::list_media`).

**Ce module ne teste ni l'une ni l'autre route isolément** (déjà couvert par
`tests/search/test_facets.py` et `tests/pipeline/test_quarantine_and_listing.py`) : il
vérifie que, pour un même jeu de données, les deux routes s'accordent sur le même ensemble
de médias — la garantie qui empêche une troisième route de réintroduire cette divergence.
Depuis le correctif, les deux routes appellent la **même** fonction
(`services/access.py::series_collapse_clause`/`exclude_duplicates_clause`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session

from apex.services.search_projection import project_media_search
from tests.conftest import auth_headers, make_user
from tests.search.factories import (
    make_camera,
    make_circuit,
    make_client,
    make_media,
    make_media_series,
    make_shooting,
    make_upload_batch,
)


@pytest.fixture
def agreement_dataset(db_session: Session):
    """Un média par catégorie susceptible d'être masquée par le collapse de séries/le
    dédoublonnage par défaut :

    | Média            | shooting | statut          | ingest_status | série                     |
    |-------------------|----------|-----------------|----------------|---------------------------|
    | `unattached`       | aucun    | unattached      | ingested       | aucune (bac « à rattacher »)|
    | `inconsistent_1/2` | S1       | inconsistent    | ingested       | aucune (non groupés)      |
    | `quarantined`       | S1       | shooting_attached | quarantined  | aucune                    |
    | `dup_master`        | S1       | shooting_attached | ingested     | aucune                    |
    | `dup_copy`          | S1       | shooting_attached | ingested     | doublon de `dup_master`   |
    | `series_repr`       | S1       | shooting_attached | ingested     | représentant              |
    | `series_member`     | S1       | shooting_attached | ingested     | membre secondaire         |

    Tous les médias non-représentatifs de série ont `is_series_representative=False`
    explicite — c'est la valeur réelle du pipeline pour tout média qui n'est jamais passé
    par `pipeline/series.py::regroup_bursts_for_shooting` (§3-G.3, `server_default="false"`
    sur `media.is_series_representative`) : la fabrique par défaut (`True`) masquait ce
    défaut jusqu'ici, cf. `tests/search/factories.py::make_media`.
    """
    owner = make_user(db_session, role="owner")
    circuit = make_circuit(db_session, "Circuit Accord")
    circuit_client = make_client(db_session, "Client Accord")
    camera = make_camera(db_session)
    base = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    shooting = make_shooting(db_session, client=circuit_client, circuit=circuit, starts_at=base)
    batch = make_upload_batch(db_session, user=owner)

    def _m(**kwargs):
        return make_media(
            db_session,
            batch=batch,
            user=owner,
            camera=camera,
            is_series_representative=False,
            **kwargs,
        )

    unattached = _m(shot_at=base, attachment_status="unattached")
    inconsistent_1 = _m(shooting=shooting, shot_at=base, attachment_status="inconsistent")
    inconsistent_2 = _m(
        shooting=shooting, shot_at=base + timedelta(minutes=1), attachment_status="inconsistent"
    )
    quarantined = _m(
        shooting=shooting,
        shot_at=base,
        attachment_status="shooting_attached",
        ingest_status="quarantined",
        quarantine_reason="truncated_file",
    )
    dup_master = _m(shooting=shooting, shot_at=base, attachment_status="shooting_attached")
    dup_copy = _m(
        shooting=shooting,
        shot_at=base,
        attachment_status="shooting_attached",
        duplicate_of_media_id=dup_master.id,
    )
    series_repr = _m(
        shooting=shooting,
        shot_at=base + timedelta(seconds=1),
        attachment_status="shooting_attached",
    )
    series_member = _m(
        shooting=shooting,
        shot_at=base + timedelta(seconds=2),
        attachment_status="shooting_attached",
    )
    make_media_series(
        db_session,
        shooting=shooting,
        camera=camera,
        members=[series_repr, series_member],
        representative=series_repr,
    )

    db_session.commit()
    project_media_search(db_session, None)
    db_session.commit()

    return {
        "owner": owner,
        "shooting": shooting,
        "unattached": unattached.id,
        "inconsistent_1": inconsistent_1.id,
        "inconsistent_2": inconsistent_2.id,
        "quarantined": quarantined.id,
        "dup_master": dup_master.id,
        "dup_copy": dup_copy.id,
        "series_repr": series_repr.id,
        "series_member": series_member.id,
    }


def _media_ids(client, headers: dict[str, str]) -> set[int]:
    payload = client.get("/api/v1/media", params={"limit": 100}, headers=headers).json()
    return {item["id"] for item in payload["items"]}


def _search_ids(client, headers: dict[str, str]) -> set[int]:
    payload = client.get("/api/v1/search", params={"limit": 100}, headers=headers).json()
    return {item["id"] for item in payload["items"]}


class TestDefaultListingsAgree:
    def test_media_and_search_show_the_same_media_on_default_listing(
        self, client, agreement_dataset
    ) -> None:
        headers = auth_headers(agreement_dataset["owner"])

        expected_visible = {
            agreement_dataset["unattached"],
            agreement_dataset["inconsistent_1"],
            agreement_dataset["inconsistent_2"],
            agreement_dataset["quarantined"],
            agreement_dataset["dup_master"],
            agreement_dataset["series_repr"],
        }
        expected_hidden = {
            agreement_dataset["dup_copy"],
            agreement_dataset["series_member"],
        }

        media_ids = _media_ids(client, headers)
        search_ids = _search_ids(client, headers)

        # Accord entre les deux routes — le cœur de la garantie demandée : elles ne
        # doivent jamais diverger sur ce qui est visible, quel que soit le motif.
        created_ids = expected_visible | expected_hidden
        assert (media_ids & created_ids) == (search_ids & created_ids), (
            "GET /media et GET /search divergent sur le même jeu de données : "
            f"/media={media_ids & created_ids}, /search={search_ids & created_ids}"
        )

        # Et cet accord doit porter sur le bon ensemble, pas seulement être mutuel — sinon
        # les deux routes pourraient masquer le même défaut de la même façon sans qu'aucun
        # test ne le voie.
        assert media_ids & created_ids == expected_visible
        assert search_ids & created_ids == expected_visible
        assert not (media_ids & expected_hidden)
        assert not (search_ids & expected_hidden)


class TestUnattachedAndInconsistentCountsAgree:
    """Reproduction directe du constat chiffré d'intégration live J2 : `status=unattached`
    et `status=inconsistent` ne doivent plus sous-compter par rapport à `GET /media`.
    """

    def test_unattached_bucket_is_not_hidden_by_search(self, client, agreement_dataset) -> None:
        headers = auth_headers(agreement_dataset["owner"])

        media_unattached = {
            item["id"]
            for item in client.get(
                "/api/v1/media", params={"limit": 100, "unattached": True}, headers=headers
            ).json()["items"]
        }
        search_payload = client.get(
            "/api/v1/search", params={"limit": 100, "status": ["unattached"]}, headers=headers
        ).json()
        search_unattached = {item["id"] for item in search_payload["items"]}

        assert agreement_dataset["unattached"] in media_unattached
        assert media_unattached == search_unattached
        assert search_payload["total"] == len(media_unattached)

    def test_inconsistent_status_is_not_undercounted_by_search(
        self, client, agreement_dataset
    ) -> None:
        headers = auth_headers(agreement_dataset["owner"])

        media_items = client.get("/api/v1/media", params={"limit": 100}, headers=headers).json()[
            "items"
        ]
        media_inconsistent = {
            item["id"] for item in media_items if item["attachment_status"] == "inconsistent"
        }
        search_payload = client.get(
            "/api/v1/search", params={"limit": 100, "status": ["inconsistent"]}, headers=headers
        ).json()
        search_inconsistent = {item["id"] for item in search_payload["items"]}

        assert media_inconsistent == {
            agreement_dataset["inconsistent_1"],
            agreement_dataset["inconsistent_2"],
        }
        assert search_inconsistent == media_inconsistent
        assert search_payload["total"] == len(media_inconsistent)
