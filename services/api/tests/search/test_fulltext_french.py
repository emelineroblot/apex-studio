"""Recherche plein texte française (`websearch_to_tsquery('french', …)`, §3-K.3) — légendes
et mots-clés pondérés `A`, pilote/écurie/numéro/circuit pondérés `B`.
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
def fulltext_dataset(db_session: Session):
    owner = make_user(db_session, role="owner")
    circuit = make_circuit(db_session, "Circuit Plein Texte")
    demo_client = make_client(db_session, "Client Plein Texte")
    team = make_team(db_session, "Écurie Mistral", demo_client)
    driver = make_driver(db_session, "Camille Fournier")
    camera = make_camera(db_session)
    base = datetime(2026, 7, 1, 10, 0, tzinfo=UTC)
    shooting = make_shooting(db_session, client=demo_client, circuit=circuit, starts_at=base)
    engagement = make_engagement(
        db_session, shooting=shooting, car_number="44", team=team, driver=driver
    )
    batch = make_upload_batch(db_session, user=owner)

    freinage = make_media(
        db_session,
        batch=batch,
        user=owner,
        shooting=shooting,
        camera=camera,
        shot_at=base,
        attachment_status="engagement_attached",
        attachment_source="pipeline_ocr",
        caption="Freinage appuyé avant l'épingle du Raidillon",
        keywords=["pluie", "sortie de piste évitée"],
        engagements=[engagement],
    )
    depart = make_media(
        db_session,
        batch=batch,
        user=owner,
        shooting=shooting,
        camera=camera,
        shot_at=base,
        attachment_status="engagement_attached",
        attachment_source="pipeline_ocr",
        caption="Départ groupé, plein soleil",
        keywords=None,
        engagements=[engagement],
    )
    sans_legende = make_media(
        db_session,
        batch=batch,
        user=owner,
        shooting=shooting,
        camera=camera,
        shot_at=base,
        attachment_status="shooting_attached",
        attachment_source="pipeline_time",
        caption=None,
        keywords=None,
    )
    db_session.commit()
    project_media_search(db_session, None)
    db_session.commit()

    return {
        "owner": owner,
        "freinage_id": freinage.id,
        "depart_id": depart.id,
        "sans_legende_id": sans_legende.id,
    }


class TestFrenchFullTextSearch:
    def test_a_word_from_the_caption_finds_only_the_matching_media(
        self, client, fulltext_dataset
    ) -> None:
        headers = auth_headers(fulltext_dataset["owner"])
        payload = client.get("/api/v1/search", headers=headers, params={"q": "freinage"}).json()
        ids = {item["id"] for item in payload["items"]}
        assert ids == {fulltext_dataset["freinage_id"]}

    def test_a_word_from_the_keywords_also_matches(self, client, fulltext_dataset) -> None:
        headers = auth_headers(fulltext_dataset["owner"])
        payload = client.get("/api/v1/search", headers=headers, params={"q": "pluie"}).json()
        ids = {item["id"] for item in payload["items"]}
        assert ids == {fulltext_dataset["freinage_id"]}

    def test_a_driver_name_matches_via_the_weighted_b_terms(self, client, fulltext_dataset) -> None:
        headers = auth_headers(fulltext_dataset["owner"])
        payload = client.get("/api/v1/search", headers=headers, params={"q": "Fournier"}).json()
        ids = {item["id"] for item in payload["items"]}
        # Les deux médias rattachés à l'engagement de Camille Fournier — pas le troisième,
        # qui n'a ni légende ni écurie/pilote associés.
        assert ids == {fulltext_dataset["freinage_id"], fulltext_dataset["depart_id"]}

    def test_websearch_syntax_supports_exclusion(self, client, fulltext_dataset) -> None:
        headers = auth_headers(fulltext_dataset["owner"])
        payload = client.get(
            "/api/v1/search", headers=headers, params={"q": "Fournier -freinage"}
        ).json()
        ids = {item["id"] for item in payload["items"]}
        assert ids == {fulltext_dataset["depart_id"]}

    def test_no_match_returns_an_empty_page_not_an_error(self, client, fulltext_dataset) -> None:
        headers = auth_headers(fulltext_dataset["owner"])
        payload = client.get(
            "/api/v1/search", headers=headers, params={"q": "mot-totalement-absent-xyz"}
        )
        assert payload.status_code == 200
        assert payload.json()["items"] == []
