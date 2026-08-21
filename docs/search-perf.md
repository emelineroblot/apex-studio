# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T21:23:55+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 8217 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 128.0 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 53.1 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 50.5 | 39.2 | 2212 |
| parcours sans filtre, tri croissant | 41.2 | 32.7 | 2212 |
| un seul shooting | 49.6 | 40.0 | 142 |
| un seul client | 37.9 | 29.7 | 238 |
| une seule écurie | 38.3 | 30.5 | 113 |
| un seul circuit | 47.1 | 39.1 | 247 |
| statut engagement_attached | 43.6 | 34.3 | 1259 |
| statut pending_review (file de validation) | 28.8 | 21.0 | 87 |
| shooting + statut combinés | 45.2 | 36.2 | 99 |
| client + écurie + statut combinés | 43.1 | 35.8 | 0 |
| plage ISO | 55.0 | 46.2 | 1643 |
| plage focale | 131.3 | 42.8 | 873 |
| plein texte, terme fréquent | 42.6 | 34.1 | 240 |
| plein texte, exclusion | 50.0 | 42.1 | 90 |
| rafales toutes (non groupées) | 55.1 | 46.4 | 8217 |
| plage de dates | 54.3 | 45.1 | 2212 |
| page 2 (curseur) | 44.8 | 35.6 | 2212 |
| grande page (limite haute) | 50.9 | 38.9 | 2212 |
| shooting inexistant (ensemble vide) | 23.5 | 16.6 | 0 |
| combinaison la plus large | 65.3 | 53.5 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
