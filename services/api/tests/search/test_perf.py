"""Mesure de performance réelle sur le jeu de démo (§3-K.2, critère d'acceptation J2 :
« la recherche reste utilisable à ~8000 médias, temps de réponse mesuré et documenté »).

Seed le jeu de démo complet une seule fois (`apex.demo.seed.run_seed`, ~8000 médias
simulés), joue 20 requêtes représentatives de l'usage réel de `/search` (parcours sans
filtre, une facette, plusieurs facettes combinées, plein texte, plages ISO/focale,
pagination), et écrit le rapport dans `docs/search-perf.md` (racine du dépôt, même
emplacement que `docs/ocr-eval.md`).
"""

from __future__ import annotations

import statistics
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.demo.seed import run_seed
from apex.models.catalog import Circuit, Client, Team
from apex.models.shooting import Shooting
from apex.models.user import AppUser
from tests.conftest import auth_headers

REPO_ROOT = Path(__file__).resolve().parents[4]
REPORT_PATH = REPO_ROOT / "docs" / "search-perf.md"

#: Budget du critère d'acceptation (§3-K.2) — mesuré, pas supposé.
P95_BUDGET_MS = 300.0


def _representative_queries(
    shooting_id: int, client_id: int, team_id: int, circuit_id: int
) -> list[tuple[str, dict[str, object]]]:
    return [
        ("parcours sans filtre (page 1)", {"limit": 60}),
        ("parcours sans filtre, tri croissant", {"limit": 60, "sort": "shot_at"}),
        ("un seul shooting", {"shooting_id": [shooting_id], "limit": 60}),
        ("un seul client", {"client_id": [client_id], "limit": 60}),
        ("une seule écurie", {"team_id": [team_id], "limit": 60}),
        ("un seul circuit", {"circuit_id": [circuit_id], "limit": 60}),
        ("statut engagement_attached", {"status": ["engagement_attached"], "limit": 60}),
        ("statut pending_review (file de validation)", {"status": ["pending_review"], "limit": 60}),
        (
            "shooting + statut combinés",
            {"shooting_id": [shooting_id], "status": ["engagement_attached"], "limit": 60},
        ),
        (
            "client + écurie + statut combinés",
            {
                "client_id": [client_id],
                "team_id": [team_id],
                "status": ["engagement_attached"],
                "limit": 60,
            },
        ),
        ("plage ISO", {"iso_min": 400, "iso_max": 1600, "limit": 60}),
        ("plage focale", {"focal_min": 70, "focal_max": 200, "limit": 60}),
        ("plein texte, terme fréquent", {"q": "virage", "limit": 60}),
        ("plein texte, exclusion", {"q": "départ -pluie", "limit": 60}),
        ("rafales toutes (non groupées)", {"series": "all", "limit": 60}),
        (
            "plage de dates",
            {
                "date_from": "2020-01-01T00:00:00+00:00",
                "date_to": "2030-01-01T00:00:00+00:00",
                "limit": 60,
            },
        ),
        ("page 2 (curseur)", {"limit": 60, "_paginate": True}),
        ("grande page (limite haute)", {"limit": 100}),
        ("shooting inexistant (ensemble vide)", {"shooting_id": [999_999], "limit": 60}),
        (
            "combinaison la plus large",
            {
                "client_id": [client_id],
                "shooting_id": [shooting_id],
                "team_id": [team_id],
                "circuit_id": [circuit_id],
                "status": ["engagement_attached", "pending_review"],
                "iso_min": 100,
                "iso_max": 6400,
                "limit": 60,
            },
        ),
    ]


def test_search_p95_latency_on_the_full_demo_dataset(client, db_session: Session) -> None:
    # Le compte `owner` vient du jeu de démo lui-même (`demo/accounts.py::ensure_demo_users`,
    # appelé par `run_seed`) — pas d'utilisateur créé séparément avant le `reset=True` : sur
    # un `RESTART IDENTITY`, un utilisateur pré-chargé dans l'identity map de **cette**
    # session entrerait en collision d'id avec celui recréé par le seed (`SAWarning`
    # bruyant, reproduit en conditions réelles — sans impact fonctionnel mais évité ici).
    result = run_seed(db_session, reset=True)
    db_session.commit()
    assert result.simulated_media >= 6000, "jeu de démo anormalement petit pour ce test"

    owner = db_session.execute(select(AppUser).where(AppUser.role == "owner")).scalar_one()
    headers = auth_headers(owner)

    shooting_id = db_session.execute(select(Shooting.id).limit(1)).scalar_one()
    client_id = db_session.execute(select(Client.id).limit(1)).scalar_one()
    team_id = db_session.execute(select(Team.id).limit(1)).scalar_one()
    circuit_id = db_session.execute(select(Circuit.id).limit(1)).scalar_one()

    queries = _representative_queries(shooting_id, client_id, team_id, circuit_id)

    measurements: list[tuple[str, float, float, int]] = []
    for label, params in queries:
        paginate = params.pop("_paginate", False)
        started = time.perf_counter()
        payload = client.get("/api/v1/search", headers=headers, params=params).json()
        wall_ms = (time.perf_counter() - started) * 1000
        if paginate and payload.get("next_cursor"):
            started2 = time.perf_counter()
            payload = client.get(
                "/api/v1/search",
                headers=headers,
                params={**params, "cursor": payload["next_cursor"]},
            ).json()
            wall_ms = (time.perf_counter() - started2) * 1000
        assert "took_ms" in payload
        measurements.append((label, wall_ms, float(payload["took_ms"]), int(payload["total"])))

    wall_times = [m[1] for m in measurements]
    server_times = [m[2] for m in measurements]
    p95_wall = statistics.quantiles(wall_times, n=100)[94]
    p95_server = statistics.quantiles(server_times, n=100)[94]

    _write_report(
        media_count=result.simulated_media + result.real_media,
        measurements=measurements,
        p95_wall=p95_wall,
        p95_server=p95_server,
    )

    # Critère d'acceptation (§3-K.2) : p95 mesuré < 300 ms — bout en bout (temps client
    # inclus, pas seulement `took_ms` côté serveur, plus strict que le budget du plan).
    assert p95_wall < P95_BUDGET_MS, (
        f"p95 mesuré {p95_wall:.1f} ms > budget {P95_BUDGET_MS} ms — voir {REPORT_PATH}"
    )


def _write_report(
    *,
    media_count: int,
    measurements: list[tuple[str, float, float, int]],
    p95_wall: float,
    p95_server: float,
) -> None:
    lines = [
        "# Performance de la recherche à facettes — mesure réelle",
        "",
        f"Généré le {datetime.now(UTC).isoformat(timespec='seconds')} par "
        "`tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.",
        "",
        f"**Jeu de démo** : {media_count} médias (`apex.demo.seed.run_seed`, graine fixe, "
        "~8000 simulés + réels si `demo-photos/` est peuplé).",
        "",
        f"**p95 (round-trip client, `TestClient` local)** : {p95_wall:.1f} ms "
        f"— budget critère d'acceptation : {P95_BUDGET_MS:.0f} ms.",
        f"**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : {p95_server:.1f} ms.",
        "",
        "| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |",
        "|---|---:|---:|---:|",
    ]
    for label, wall_ms, server_ms, total in measurements:
        lines.append(f"| {label} | {wall_ms:.1f} | {server_ms:.1f} | {total} |")
    lines += [
        "",
        "## Méthode",
        "",
        "- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles "
        "en rejouant `uv run pytest tests/search/test_perf.py -q`.",
        "- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, "
        "une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, "
        "pagination par curseur, ensemble vide, combinaison la plus large.",
        "- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base "
        "Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat "
        "(`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).",
        "- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, "
        "conteneur Docker), pas d'environnement de production — les temps réels côté Neon/"
        "Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
