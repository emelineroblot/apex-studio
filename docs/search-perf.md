# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T18:42:18+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 8217 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 87.2 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 69.4 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 50.7 | 40.6 | 2212 |
| parcours sans filtre, tri croissant | 39.8 | 32.1 | 2212 |
| un seul shooting | 45.8 | 37.1 | 142 |
| un seul client | 44.4 | 36.5 | 238 |
| une seule écurie | 37.9 | 30.9 | 113 |
| un seul circuit | 43.6 | 36.5 | 247 |
| statut engagement_attached | 39.2 | 31.8 | 1259 |
| statut pending_review (file de validation) | 27.1 | 20.3 | 87 |
| shooting + statut combinés | 41.4 | 34.4 | 99 |
| client + écurie + statut combinés | 37.7 | 31.1 | 0 |
| plage ISO | 49.4 | 42.2 | 1643 |
| plage focale | 87.7 | 60.5 | 873 |
| plein texte, terme fréquent | 40.2 | 32.4 | 240 |
| plein texte, exclusion | 45.3 | 37.6 | 90 |
| rafales toutes (non groupées) | 78.1 | 69.8 | 8217 |
| plage de dates | 47.3 | 40.1 | 2212 |
| page 2 (curseur) | 66.0 | 36.1 | 2212 |
| grande page (limite haute) | 47.1 | 38.0 | 2212 |
| shooting inexistant (ensemble vide) | 23.0 | 16.1 | 0 |
| combinaison la plus large | 53.5 | 45.2 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
