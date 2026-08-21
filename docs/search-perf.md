# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T20:36:57+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 8217 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 51.3 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 44.1 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 46.5 | 35.5 | 2212 |
| parcours sans filtre, tri croissant | 40.8 | 32.2 | 2212 |
| un seul shooting | 42.4 | 34.2 | 142 |
| un seul client | 36.9 | 28.9 | 238 |
| une seule écurie | 37.4 | 29.2 | 113 |
| un seul circuit | 42.8 | 34.6 | 247 |
| statut engagement_attached | 39.0 | 31.2 | 1259 |
| statut pending_review (file de validation) | 29.4 | 21.2 | 87 |
| shooting + statut combinés | 46.4 | 36.4 | 99 |
| client + écurie + statut combinés | 36.2 | 29.5 | 0 |
| plage ISO | 48.7 | 40.6 | 1643 |
| plage focale | 46.1 | 38.6 | 873 |
| plein texte, terme fréquent | 39.8 | 32.4 | 240 |
| plein texte, exclusion | 42.7 | 35.7 | 90 |
| rafales toutes (non groupées) | 51.4 | 44.3 | 8217 |
| plage de dates | 46.0 | 38.3 | 2212 |
| page 2 (curseur) | 41.9 | 34.4 | 2212 |
| grande page (limite haute) | 39.2 | 31.6 | 2212 |
| shooting inexistant (ensemble vide) | 20.6 | 14.3 | 0 |
| combinaison la plus large | 45.4 | 39.2 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
