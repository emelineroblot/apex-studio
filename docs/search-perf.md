# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T22:17:14+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 8217 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 125.5 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 118.1 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 47.5 | 36.6 | 2212 |
| parcours sans filtre, tri croissant | 44.8 | 35.7 | 2212 |
| un seul shooting | 44.3 | 37.2 | 142 |
| un seul client | 34.8 | 27.6 | 238 |
| une seule écurie | 42.1 | 32.9 | 113 |
| un seul circuit | 47.0 | 40.1 | 247 |
| statut engagement_attached | 56.9 | 47.4 | 1259 |
| statut pending_review (file de validation) | 34.8 | 26.4 | 87 |
| shooting + statut combinés | 40.8 | 33.2 | 99 |
| client + écurie + statut combinés | 38.2 | 32.1 | 0 |
| plage ISO | 54.3 | 47.0 | 1643 |
| plage focale | 52.2 | 45.0 | 873 |
| plein texte, terme fréquent | 38.8 | 32.0 | 240 |
| plein texte, exclusion | 129.1 | 121.8 | 90 |
| rafales toutes (non groupées) | 55.1 | 47.4 | 8217 |
| plage de dates | 46.6 | 39.4 | 2212 |
| page 2 (curseur) | 41.9 | 33.7 | 2212 |
| grande page (limite haute) | 42.3 | 34.1 | 2212 |
| shooting inexistant (ensemble vide) | 21.2 | 14.6 | 0 |
| combinaison la plus large | 49.5 | 42.3 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
