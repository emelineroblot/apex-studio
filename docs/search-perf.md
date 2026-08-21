# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T03:12:50+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 8472 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 51.9 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 45.3 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 43.9 | 35.3 | 1427 |
| parcours sans filtre, tri croissant | 35.1 | 29.1 | 1427 |
| un seul shooting | 29.4 | 23.6 | 114 |
| un seul client | 28.6 | 23.0 | 158 |
| une seule écurie | 31.4 | 24.2 | 136 |
| un seul circuit | 29.3 | 23.6 | 179 |
| statut engagement_attached | 40.2 | 34.3 | 1176 |
| statut pending_review (file de validation) | 27.3 | 20.6 | 68 |
| shooting + statut combinés | 29.5 | 24.1 | 90 |
| client + écurie + statut combinés | 27.6 | 22.6 | 0 |
| plage ISO | 41.7 | 35.6 | 1183 |
| plage focale | 46.7 | 40.1 | 625 |
| plein texte, terme fréquent | 36.9 | 30.5 | 186 |
| plein texte, exclusion | 42.7 | 36.2 | 84 |
| rafales toutes (non groupées) | 52.1 | 45.6 | 8472 |
| plage de dates | 47.9 | 40.8 | 1427 |
| page 2 (curseur) | 35.4 | 28.9 | 1427 |
| grande page (limite haute) | 38.3 | 31.6 | 1427 |
| shooting inexistant (ensemble vide) | 20.7 | 14.3 | 0 |
| combinaison la plus large | 29.7 | 24.4 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
