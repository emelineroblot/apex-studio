# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T05:23:48+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 7917 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 66.8 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 58.5 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 41.4 | 33.6 | 1912 |
| parcours sans filtre, tri croissant | 33.7 | 27.9 | 1912 |
| un seul shooting | 28.4 | 22.8 | 122 |
| un seul client | 30.1 | 24.1 | 198 |
| une seule écurie | 29.9 | 23.1 | 122 |
| un seul circuit | 30.5 | 24.7 | 207 |
| statut engagement_attached | 39.2 | 33.1 | 1259 |
| statut pending_review (file de validation) | 28.3 | 21.7 | 87 |
| shooting + statut combinés | 32.8 | 26.8 | 99 |
| client + écurie + statut combinés | 30.3 | 24.3 | 0 |
| plage ISO | 43.2 | 36.7 | 1560 |
| plage focale | 42.0 | 35.9 | 823 |
| plein texte, terme fréquent | 36.6 | 30.4 | 240 |
| plein texte, exclusion | 40.4 | 34.2 | 90 |
| rafales toutes (non groupées) | 50.0 | 43.6 | 7917 |
| plage de dates | 67.6 | 59.3 | 1912 |
| page 2 (curseur) | 38.4 | 31.6 | 1912 |
| grande page (limite haute) | 36.4 | 30.1 | 1912 |
| shooting inexistant (ensemble vide) | 18.1 | 13.0 | 0 |
| combinaison la plus large | 27.8 | 22.8 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
