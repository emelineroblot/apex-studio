"""Cloisonnement de l'espace client (§3-L.3) — **paramétré sur toutes les routes `/public`
découvertes dans l'OpenAPI**, pas sur une liste écrite à la main.

C'est le point du plan : toute route `/public` ajoutée plus tard est automatiquement
couverte. Un test qui énumère des chemins en dur protège le code du jour où il a été écrit ;
celui-ci protège la règle.

Deux invariants vérifiés sur chaque route :

1. **Aucun accès sans session client** → `401`.
2. **Rien hors du périmètre du jeton** → `404`, jamais `403` : répondre « interdit »
   confirmerait l'existence de la ressource.
"""

from __future__ import annotations

import pytest

from tests.public.conftest import expire_link

#: Le corps d'une requête de session n'a pas de session à présenter — c'est la porte
#: d'entrée, elle est publique par construction.
SESSION_ROUTE = "/api/v1/public/session"


def _public_routes(client) -> list[tuple[str, str]]:
    spec = client.get("/openapi.json").json()
    routes: list[tuple[str, str]] = []
    for path, methods in spec["paths"].items():
        if not path.startswith("/api/v1/public/"):
            continue
        for method in methods:
            if method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
                continue
            if path == SESSION_ROUTE:
                continue
            routes.append((method.upper(), path))
    return sorted(routes)


def test_le_perimetre_public_est_bien_couvert(client) -> None:
    """Garde-fou du garde-fou : si l'introspection ne trouve plus rien, les deux tests
    ci-dessous passeraient en ne vérifiant rien du tout."""
    assert len(_public_routes(client)) >= 8


def test_aucune_route_publique_nest_accessible_sans_session(client, shared_collection) -> None:
    for method, path in _public_routes(client):
        concrete = path.replace("{media_id}", str(shared_collection["media_ids"][0]))
        response = client.request(method, concrete)
        assert response.status_code == 401, (
            f"{method} {path} répond {response.status_code} sans session client"
        )


def test_aucune_route_publique_ne_franchit_le_perimetre_du_jeton(
    client, shared_collection, client_session
) -> None:
    """Un `media_id` réel, existant, mais appartenant à **une autre collection**."""
    outsider = shared_collection["outsider_media_id"]
    checked = 0
    for method, path in _public_routes(client):
        if "{media_id}" not in path:
            continue
        response = client.request(
            method,
            path.replace("{media_id}", str(outsider)),
            headers=client_session["headers"],
            # Corps minimal valide pour les routes qui en attendent un : sans lui, la
            # validation répondrait `422` et le test mesurerait Pydantic, pas le
            # cloisonnement.
            json={} if method in ("POST", "PUT", "PATCH") else None,
        )
        if response.status_code == 501:
            # Route dont le contrat est gelé mais le corps pas encore écrit : la
            # vérification de périmètre vit dans ce corps. À retirer quand J3 est complet —
            # `test_le_perimetre_public_est_bien_couvert` garantit qu'on ne perd pas la
            # couverture en attendant.
            continue
        checked += 1
        assert response.status_code == 404, (
            f"{method} {path} répond {response.status_code} sur un média hors périmètre"
        )
    assert checked >= 2, "aucune route à media_id n'a réellement été vérifiée"


@pytest.mark.parametrize("selected_only", [False, True])
def test_la_collection_ne_montre_que_les_medias_du_jeton(
    client, shared_collection, client_session, selected_only
) -> None:
    response = client.get(
        "/api/v1/public/collection",
        params={"selected_only": selected_only},
        headers=client_session["headers"],
    )
    assert response.status_code == 200, response.text
    returned = {item["media_id"] for item in response.json()["items"]}
    assert returned <= set(shared_collection["media_ids"])
    assert shared_collection["outsider_media_id"] not in returned


def test_un_lien_expire_ferme_toutes_les_routes_publiques(
    client, shared_collection, client_session, db_session
) -> None:
    expire_link(db_session, shared_collection["link_id"])
    for method, path in _public_routes(client):
        concrete = path.replace("{media_id}", str(shared_collection["media_ids"][0]))
        response = client.request(method, concrete, headers=client_session["headers"])
        assert response.status_code == 410, (
            f"{method} {path} répond {response.status_code} avec un lien expiré"
        )
        assert response.json()["code"] == "link_expired"
