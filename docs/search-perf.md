# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T20:47:11+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 8217 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 52.7 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 44.6 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 46.7 | 35.5 | 2212 |
| parcours sans filtre, tri croissant | 40.1 | 31.8 | 2212 |
| un seul shooting | 34.0 | 26.2 | 142 |
| un seul client | 34.6 | 27.2 | 238 |
| une seule écurie | 32.2 | 25.0 | 113 |
| un seul circuit | 34.0 | 26.7 | 247 |
| statut engagement_attached | 39.8 | 31.6 | 1259 |
| statut pending_review (file de validation) | 28.3 | 20.8 | 87 |
| shooting + statut combinés | 34.6 | 27.0 | 99 |
| client + écurie + statut combinés | 31.8 | 24.6 | 0 |
| plage ISO | 48.4 | 40.0 | 1643 |
| plage focale | 45.4 | 37.7 | 873 |
| plein texte, terme fréquent | 41.5 | 33.5 | 240 |
| plein texte, exclusion | 43.6 | 35.5 | 90 |
| rafales toutes (non groupées) | 52.9 | 44.8 | 8217 |
| plage de dates | 49.1 | 41.1 | 2212 |
| page 2 (curseur) | 40.0 | 32.2 | 2212 |
| grande page (limite haute) | 40.4 | 31.9 | 2212 |
| shooting inexistant (ensemble vide) | 22.1 | 15.1 | 0 |
| combinaison la plus large | 32.4 | 25.3 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
