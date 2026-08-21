"""Pagination keyset `(shot_at, media_id)` (§3-K.2) — jamais d'`OFFSET`.

Vérifie l'absence de doublon/omission en parcourant toutes les pages, dans les deux sens de
tri, y compris le cas `shot_at IS NULL` (média sans horodatage exploitable, § pieges-projet
« un motif de quarantaine peut laisser `shot_at` vide »).
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
    make_shooting,
    make_upload_batch,
)


@pytest.fixture
def paginated_dataset(db_session: Session):
    owner = make_user(db_session, role="owner")
    circuit = make_circuit(db_session, "Circuit Pagination")
    demo_client = make_client(db_session, "Client Pagination")
    camera = make_camera(db_session)
    base = datetime(2026, 6, 1, 9, 0, tzinfo=UTC)
    shooting = make_shooting(db_session, client=demo_client, circuit=circuit, starts_at=base)
    batch = make_upload_batch(db_session, user=owner)

    media_ids: list[int] = []
    for i in range(23):
        media = make_media(
            db_session,
            batch=batch,
            user=owner,
            shooting=shooting,
            camera=camera,
            shot_at=base + timedelta(minutes=i),
            attachment_status="shooting_attached",
            attachment_source="pipeline_time",
        )
        media_ids.append(media.id)

    # Trois médias sans `shot_at` exploitable (quarantaine précoce, § pieges-projet).
    for _i in range(3):
        media = make_media(
            db_session,
            batch=batch,
            user=owner,
            shooting=None,
            camera=None,
            shot_at=base,  # requis par la fabrique, écrasé juste après
            attachment_status="unattached",
        )
        media.shot_at = None
        db_session.flush()
        media_ids.append(media.id)

    db_session.commit()
    project_media_search(db_session, None)
    db_session.commit()
    return {"owner": owner, "media_ids": set(media_ids)}


def _collect_all_pages(client, headers, *, sort: str, limit: int) -> list[int]:
    seen: list[int] = []
    cursor: str | None = None
    guard = 0
    while True:
        guard += 1
        assert guard < 100, "boucle de pagination anormalement longue"
        params: dict[str, object] = {"sort": sort, "limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        payload = client.get("/api/v1/search", headers=headers, params=params).json()
        seen.extend(item["id"] for item in payload["items"])
        cursor = payload["next_cursor"]
        if cursor is None:
            break
    return seen


class TestKeysetPaginationIsStableAndExhaustive:
    @pytest.mark.parametrize("sort", ["-shot_at", "shot_at"])
    def test_every_page_together_covers_the_dataset_without_duplicates(
        self, client, paginated_dataset, sort: str
    ) -> None:
        headers = auth_headers(paginated_dataset["owner"])
        seen = _collect_all_pages(client, headers, sort=sort, limit=5)

        assert len(seen) == len(set(seen)), "un média est apparu deux fois sur deux pages"
        assert set(seen) == paginated_dataset["media_ids"]

    def test_descending_sort_orders_most_recent_first(self, client, paginated_dataset) -> None:
        headers = auth_headers(paginated_dataset["owner"])
        payload = client.get(
            "/api/v1/search", headers=headers, params={"sort": "-shot_at", "limit": 100}
        ).json()
        shot_ats = [item["shot_at"] for item in payload["items"] if item["shot_at"] is not None]
        assert shot_ats == sorted(shot_ats, reverse=True)
        # Les médias sans `shot_at` sont en toute fin de page (NULLS LAST, § docstring).
        null_positions = [i for i, item in enumerate(payload["items"]) if item["shot_at"] is None]
        assert null_positions == sorted(null_positions)
        if null_positions:
            assert min(null_positions) > len(shot_ats) - 1

    def test_a_stale_cursor_beyond_the_dataset_yields_an_empty_page(
        self, client, paginated_dataset
    ) -> None:
        headers = auth_headers(paginated_dataset["owner"])
        # Curseur syntaxiquement valide mais pointant après le dernier élément.
        import base64
        import json

        # Tri ascendant : la partition `shot_at IS NULL` est triée par `media_id` croissant
        # — un curseur `id` très supérieur au dernier média simulé la place « après tout ».
        stale = base64.urlsafe_b64encode(json.dumps({"t": None, "id": 999_999}).encode()).decode()
        payload = client.get(
            "/api/v1/search", headers=headers, params={"cursor": stale, "sort": "shot_at"}
        ).json()
        assert payload["items"] == []
        assert payload["next_cursor"] is None

    def test_an_invalid_cursor_is_rejected_with_400(self, client, paginated_dataset) -> None:
        headers = auth_headers(paginated_dataset["owner"])
        resp = client.get(
            "/api/v1/search", headers=headers, params={"cursor": "not-a-valid-cursor!!"}
        )
        assert resp.status_code == 400
        assert resp.json()["code"] == "invalid_cursor"
