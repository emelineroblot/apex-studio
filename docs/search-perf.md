# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T19:53:49+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 8217 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 53.2 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 45.4 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 49.0 | 37.3 | 2212 |
| parcours sans filtre, tri croissant | 40.9 | 33.6 | 2212 |
| un seul shooting | 43.4 | 36.1 | 142 |
| un seul client | 34.6 | 27.7 | 238 |
| une seule écurie | 34.8 | 28.0 | 113 |
| un seul circuit | 43.6 | 35.9 | 247 |
| statut engagement_attached | 38.3 | 30.4 | 1259 |
| statut pending_review (file de validation) | 25.9 | 18.8 | 87 |
| shooting + statut combinés | 41.3 | 34.0 | 99 |
| client + écurie + statut combinés | 36.5 | 30.1 | 0 |
| plage ISO | 51.2 | 43.8 | 1643 |
| plage focale | 49.3 | 40.7 | 873 |
| plein texte, terme fréquent | 39.2 | 32.0 | 240 |
| plein texte, exclusion | 46.9 | 39.1 | 90 |
| rafales toutes (non groupées) | 53.3 | 45.4 | 8217 |
| plage de dates | 49.7 | 41.0 | 2212 |
| page 2 (curseur) | 39.8 | 32.3 | 2212 |
| grande page (limite haute) | 42.9 | 34.5 | 2212 |
| shooting inexistant (ensemble vide) | 20.8 | 14.2 | 0 |
| combinaison la plus large | 47.1 | 40.8 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
