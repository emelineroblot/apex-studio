"""Compteurs de facettes « sauf soi » (§3-K.2 du plan) — jeu construit à la main,
calculable de tête (même méthode que `tests/ocr/test_classification.py`).

Scénario (2 shootings, 2 écuries, 1 pilote partagé, 5 médias) :

| Média | Shooting | Écurie (via engagement) | Statut               |
|-------|----------|--------------------------|-----------------------|
| M1    | S1       | T1 (n°12)                 | engagement_attached  |
| M2    | S1       | T1 (n°12)                 | engagement_attached  |
| M3    | S2       | T2 (n°7)                  | engagement_attached  |
| M4    | S1       | —                          | shooting_attached    |
| M5    | S2       | —                          | shooting_attached    |

Client Cl1 possède S1, Cl2 possède S2 (`client_id` de la facette vient du shooting, §3-K.1).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from apex.services.search_projection import project_media_search
from tests.conftest import auth_headers, make_user
from tests.search.factories import (
    make_camera,
    make_circuit,
    make_client,
    make_driver,
    make_engagement,
    make_media,
    make_shooting,
    make_team,
    make_upload_batch,
)


@pytest.fixture
def hand_built_dataset(db_session: Session):
    owner = make_user(db_session, role="owner")
    circuit = make_circuit(db_session, "Circuit Test")
    client1 = make_client(db_session, "Client Un")
    client2 = make_client(db_session, "Client Deux")
    team1 = make_team(db_session, "Écurie Un", client1)
    team2 = make_team(db_session, "Écurie Deux", client2)
    driver = make_driver(db_session, "Pilote Commun")
    camera = make_camera(db_session)

    base = datetime(2026, 5, 1, 10, 0, tzinfo=UTC)
    shooting1 = make_shooting(db_session, client=client1, circuit=circuit, starts_at=base)
    shooting2 = make_shooting(db_session, client=client2, circuit=circuit, starts_at=base)

    engagement1 = make_engagement(
        db_session, shooting=shooting1, car_number="12", team=team1, driver=driver
    )
    engagement2 = make_engagement(
        db_session, shooting=shooting2, car_number="7", team=team2, driver=driver
    )

    batch = make_upload_batch(db_session, user=owner)
    m1 = make_media(
        db_session,
        batch=batch,
        user=owner,
        shooting=shooting1,
        camera=camera,
        shot_at=base,
        attachment_status="engagement_attached",
        attachment_source="pipeline_ocr",
        engagements=[engagement1],
    )
    m2 = make_media(
        db_session,
        batch=batch,
        user=owner,
        shooting=shooting1,
        camera=camera,
        shot_at=base,
        attachment_status="engagement_attached",
        attachment_source="pipeline_ocr",
        engagements=[engagement1],
    )
    m3 = make_media(
        db_session,
        batch=batch,
        user=owner,
        shooting=shooting2,
        camera=camera,
        shot_at=base,
        attachment_status="engagement_attached",
        attachment_source="pipeline_ocr",
        engagements=[engagement2],
    )
    m4 = make_media(
        db_session,
        batch=batch,
        user=owner,
        shooting=shooting1,
        camera=camera,
        shot_at=base,
        attachment_status="shooting_attached",
        attachment_source="pipeline_time",
    )
    m5 = make_media(
        db_session,
        batch=batch,
        user=owner,
        shooting=shooting2,
        camera=camera,
        shot_at=base,
        attachment_status="shooting_attached",
        attachment_source="pipeline_time",
    )
    db_session.commit()
    project_media_search(db_session, None)
    db_session.commit()

    return {
        "owner": owner,
        "team1": team1,
        "team2": team2,
        "shooting1": shooting1,
        "shooting2": shooting2,
        "media": {"m1": m1.id, "m2": m2.id, "m3": m3.id, "m4": m4.id, "m5": m5.id},
    }


def _facet_counts(facet_list: list[dict], key: str = "id") -> dict[int, int]:
    return {item[key]: item["count"] for item in facet_list}


class TestFacetCountsWithoutFilter:
    def test_all_facets_reflect_the_whole_dataset(self, client, hand_built_dataset) -> None:
        headers = auth_headers(hand_built_dataset["owner"])
        payload = client.get("/api/v1/search", headers=headers).json()

        assert payload["total"] == 5
        shooting_counts = _facet_counts(payload["facets"]["shooting"])
        assert shooting_counts[hand_built_dataset["shooting1"].id] == 3
        assert shooting_counts[hand_built_dataset["shooting2"].id] == 2

        team_counts = _facet_counts(payload["facets"]["team"])
        assert team_counts[hand_built_dataset["team1"].id] == 2
        assert team_counts[hand_built_dataset["team2"].id] == 1

        status_counts = {item["value"]: item["count"] for item in payload["facets"]["status"]}
        assert status_counts["engagement_attached"] == 3
        assert status_counts["shooting_attached"] == 2


class TestFacetCountsExcludeOwnFilter:
    def test_team_filter_narrows_results_but_not_the_team_facet_itself(
        self, client, hand_built_dataset
    ) -> None:
        headers = auth_headers(hand_built_dataset["owner"])
        team1_id = hand_built_dataset["team1"].id
        team2_id = hand_built_dataset["team2"].id
        shooting1_id = hand_built_dataset["shooting1"].id

        payload = client.get(
            "/api/v1/search", headers=headers, params={"team_id": [team1_id]}
        ).json()

        # Résultats : seuls M1/M2 (écurie 1) — la règle « sauf soi » ne change rien ici,
        # le filtre s'applique bien aux items renvoyés.
        assert payload["total"] == 2

        # La facette « équipe » elle-même reste celle du jeu ENTIER (règle « sauf soi »,
        # §3-K.2) : cocher l'écurie 1 ne doit pas faire tomber l'écurie 2 à zéro, sinon le
        # filtre deviendrait inutilisable.
        team_counts = _facet_counts(payload["facets"]["team"])
        assert team_counts[team1_id] == 2
        assert team_counts[team2_id] == 1

        # La facette « shooting », elle, N'EST PAS la facette filtrée : elle reflète le jeu
        # filtré par l'équipe (shooting 2 disparaît, aucun de ses médias n'a l'écurie 1).
        shooting_counts = _facet_counts(payload["facets"]["shooting"])
        assert shooting_counts == {shooting1_id: 2}

    def test_two_simultaneous_multi_select_facets_each_exclude_only_themselves(
        self, client, hand_built_dataset
    ) -> None:
        headers = auth_headers(hand_built_dataset["owner"])
        team1_id = hand_built_dataset["team1"].id
        team2_id = hand_built_dataset["team2"].id

        payload = client.get(
            "/api/v1/search",
            headers=headers,
            params={"team_id": [team1_id], "status": ["engagement_attached"]},
        ).json()

        # M1 + M2 seuls satisfont écurie 1 ET statut engagement_attached.
        assert payload["total"] == 2

        # Facette équipe : « sauf soi » => le filtre de statut reste appliqué, celui
        # d'équipe est ignoré pour ce calcul. Tous les médias `engagement_attached`
        # (M1, M2, M3) ont une écurie : T1:2, T2:1 — identique au cas sans aucun filtre.
        team_counts = _facet_counts(payload["facets"]["team"])
        assert team_counts[team1_id] == 2
        assert team_counts[team2_id] == 1

        # Facette statut : « sauf soi » => le filtre d'équipe reste appliqué, celui de
        # statut est ignoré. Parmi les médias de l'écurie 1 (M1, M2 — M4 n'a pas
        # d'engagement, donc pas d'écurie), les deux sont `engagement_attached`.
        status_counts = {item["value"]: item["count"] for item in payload["facets"]["status"]}
        assert status_counts == {"engagement_attached": 2}
