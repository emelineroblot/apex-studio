# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T06:07:24+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 7917 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 78.8 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 68.8 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 49.4 | 40.3 | 1912 |
| parcours sans filtre, tri croissant | 49.2 | 40.0 | 1912 |
| un seul shooting | 46.4 | 35.3 | 122 |
| un seul client | 36.1 | 29.4 | 198 |
| une seule écurie | 38.6 | 32.1 | 113 |
| un seul circuit | 40.3 | 32.6 | 207 |
| statut engagement_attached | 48.3 | 40.1 | 1259 |
| statut pending_review (file de validation) | 41.9 | 32.3 | 87 |
| shooting + statut combinés | 44.8 | 37.1 | 99 |
| client + écurie + statut combinés | 51.1 | 44.2 | 0 |
| plage ISO | 58.7 | 51.3 | 1560 |
| plage focale | 79.9 | 69.7 | 823 |
| plein texte, terme fréquent | 53.3 | 43.7 | 240 |
| plein texte, exclusion | 58.8 | 51.5 | 90 |
| rafales toutes (non groupées) | 57.1 | 49.9 | 7917 |
| plage de dates | 54.6 | 47.4 | 1912 |
| page 2 (curseur) | 46.3 | 35.9 | 1912 |
| grande page (limite haute) | 48.4 | 38.6 | 1912 |
| shooting inexistant (ensemble vide) | 26.9 | 18.9 | 0 |
| combinaison la plus large | 39.3 | 33.0 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
