# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T03:55:32+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 8472 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 55.0 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 48.2 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 43.7 | 34.8 | 2066 |
| parcours sans filtre, tri croissant | 38.7 | 32.0 | 2066 |
| un seul shooting | 31.2 | 25.2 | 133 |
| un seul client | 32.7 | 26.5 | 189 |
| une seule écurie | 31.0 | 24.8 | 156 |
| un seul circuit | 40.0 | 33.6 | 207 |
| statut engagement_attached | 41.7 | 35.4 | 1389 |
| statut pending_review (file de validation) | 28.3 | 21.7 | 80 |
| shooting + statut combinés | 34.2 | 27.9 | 104 |
| client + écurie + statut combinés | 30.5 | 24.8 | 0 |
| plage ISO | 46.4 | 39.0 | 1702 |
| plage focale | 51.6 | 44.2 | 902 |
| plein texte, terme fréquent | 40.6 | 32.7 | 260 |
| plein texte, exclusion | 45.4 | 38.1 | 109 |
| rafales toutes (non groupées) | 55.2 | 48.4 | 8472 |
| plage de dates | 47.4 | 40.9 | 2066 |
| page 2 (curseur) | 38.9 | 32.1 | 2066 |
| grande page (limite haute) | 40.6 | 33.8 | 2066 |
| shooting inexistant (ensemble vide) | 20.3 | 14.5 | 0 |
| combinaison la plus large | 31.5 | 26.1 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
