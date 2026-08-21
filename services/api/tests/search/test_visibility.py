"""Cloisonnement de rôle sur `GET /search` (revue J2, 🟠 n°4) — manquant jusqu'ici.

`services/facets.py::visibility_clause` réimplémentait `access.py::media_visibility_clause`
en propre plutôt que de la partager (§ docstring de `facets.py::visibility_clause`) : rien
ne prouvait que la recherche respectait la même matrice de rôles que `/media` et
`/review/queue`. Scénario : deux shootings, un photographe affecté au premier seulement,
plus un média qu'il a lui-même déposé mais pas encore rattaché (`shooting_id IS NULL`) —
c'est le cas que `access.media_visibility_clause_for` traite spécifiquement (bac « à
rattacher »).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from apex.models.shooting import ShootingStaff
from tests.conftest import auth_headers, make_user
from tests.search.factories import (
    make_camera,
    make_circuit,
    make_client,
    make_media,
    make_shooting,
    make_upload_batch,
)


def test_search_never_leaks_a_media_outside_the_photographers_assigned_shootings(
    client, db_session: Session
) -> None:
    owner = make_user(db_session, role="owner", email="owner-search-vis@apex-test.dev")
    photographer_a = make_user(
        db_session, role="photographer", email="photog-search-vis-a@apex-test.dev"
    )
    photographer_b = make_user(
        db_session, role="photographer", email="photog-search-vis-b@apex-test.dev"
    )
    circuit = make_circuit(db_session, "Circuit Cloisonnement")
    client_a = make_client(db_session, "Client Cloisonnement A")
    client_b = make_client(db_session, "Client Cloisonnement B")
    camera = make_camera(db_session)
    base = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)

    shooting_a = make_shooting(db_session, client=client_a, circuit=circuit, starts_at=base)
    shooting_b = make_shooting(db_session, client=client_b, circuit=circuit, starts_at=base)
    db_session.add(ShootingStaff(shooting_id=shooting_a.id, user_id=photographer_a.id, role="lead"))
    db_session.flush()

    batch = make_upload_batch(db_session, user=photographer_a)
    media_a = make_media(
        db_session,
        batch=batch,
        user=photographer_a,
        shooting=shooting_a,
        camera=camera,
        shot_at=base,
        attachment_status="shooting_attached",
        attachment_source="pipeline_time",
    )
    media_b = make_media(
        db_session,
        batch=make_upload_batch(db_session, user=owner),
        user=owner,
        shooting=shooting_b,
        camera=camera,
        shot_at=base,
        attachment_status="shooting_attached",
        attachment_source="pipeline_time",
    )
    # Bac « à rattacher » : déposé par le photographe A, aucun shooting encore — doit rester
    # visible pour lui malgré l'absence de `shooting_id` (`media_visibility_clause_for`).
    media_unattached = make_media(
        db_session,
        batch=batch,
        user=photographer_a,
        shooting=None,
        camera=camera,
        shot_at=base,
        attachment_status="unattached",
    )
    db_session.commit()

    from apex.services.search_projection import project_media_search

    project_media_search(db_session, None)
    db_session.commit()

    resp_a = client.get("/api/v1/search", headers=auth_headers(photographer_a))
    assert resp_a.status_code == 200
    ids_a = {item["id"] for item in resp_a.json()["items"]}
    assert ids_a == {media_a.id, media_unattached.id}
    assert media_b.id not in ids_a

    # La facette « shooting » elle-même ne doit pas fuiter le shooting hors périmètre.
    shooting_facet_ids = {row["id"] for row in resp_a.json()["facets"]["shooting"]}
    assert shooting_b.id not in shooting_facet_ids

    resp_b = client.get("/api/v1/search", headers=auth_headers(photographer_b))
    assert resp_b.status_code == 200
    assert resp_b.json()["items"] == []

    resp_owner = client.get("/api/v1/search", headers=auth_headers(owner))
    assert resp_owner.status_code == 200
    ids_owner = {item["id"] for item in resp_owner.json()["items"]}
    assert ids_owner == {media_a.id, media_b.id, media_unattached.id}
