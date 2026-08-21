# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T22:36:52+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 8217 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 136.5 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 122.4 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 46.6 | 34.6 | 2212 |
| parcours sans filtre, tri croissant | 37.6 | 30.2 | 2212 |
| un seul shooting | 41.5 | 34.8 | 142 |
| un seul client | 41.0 | 27.7 | 238 |
| une seule écurie | 36.9 | 29.2 | 113 |
| un seul circuit | 44.3 | 36.1 | 247 |
| statut engagement_attached | 38.2 | 31.4 | 1259 |
| statut pending_review (file de validation) | 25.8 | 19.1 | 87 |
| shooting + statut combinés | 38.2 | 31.2 | 99 |
| client + écurie + statut combinés | 37.3 | 30.4 | 0 |
| plage ISO | 47.0 | 38.8 | 1643 |
| plage focale | 48.9 | 42.1 | 873 |
| plein texte, terme fréquent | 39.8 | 31.9 | 240 |
| plein texte, exclusion | 140.8 | 126.4 | 90 |
| rafales toutes (non groupées) | 55.0 | 47.4 | 8217 |
| plage de dates | 49.8 | 42.2 | 2212 |
| page 2 (curseur) | 36.4 | 29.8 | 2212 |
| grande page (limite haute) | 38.6 | 31.7 | 2212 |
| shooting inexistant (ensemble vide) | 19.7 | 13.9 | 0 |
| combinaison la plus large | 42.9 | 37.0 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
