# Performance de la recherche à facettes — mesure réelle

Généré le 2026-08-21T05:00:22+00:00 par `tests/search/test_perf.py::test_search_p95_latency_on_the_full_demo_dataset`.

**Jeu de démo** : 7917 médias (`apex.demo.seed.run_seed`, graine fixe, ~8000 simulés + réels si `demo-photos/` est peuplé).

**p95 (round-trip client, `TestClient` local)** : 52.4 ms — budget critère d'acceptation : 300 ms.
**p95 (`took_ms`, mesuré côté serveur, exposé dans la réponse)** : 45.3 ms.

| Requête | Round-trip (ms) | `took_ms` serveur (ms) | Résultats totaux |
|---|---:|---:|---:|
| parcours sans filtre (page 1) | 44.4 | 35.2 | 1912 |
| parcours sans filtre, tri croissant | 38.0 | 31.3 | 1912 |
| un seul shooting | 42.4 | 35.5 | 122 |
| un seul client | 37.7 | 29.3 | 198 |
| une seule écurie | 35.6 | 28.7 | 122 |
| un seul circuit | 41.4 | 35.0 | 207 |
| statut engagement_attached | 38.2 | 31.9 | 1259 |
| statut pending_review (file de validation) | 27.6 | 20.9 | 87 |
| shooting + statut combinés | 43.0 | 35.6 | 99 |
| client + écurie + statut combinés | 40.0 | 31.9 | 0 |
| plage ISO | 46.8 | 40.2 | 1560 |
| plage focale | 48.6 | 41.6 | 823 |
| plein texte, terme fréquent | 43.7 | 35.5 | 240 |
| plein texte, exclusion | 49.8 | 43.2 | 90 |
| rafales toutes (non groupées) | 52.5 | 45.4 | 7917 |
| plage de dates | 45.1 | 38.4 | 1912 |
| page 2 (curseur) | 38.8 | 32.1 | 1912 |
| grande page (limite haute) | 38.9 | 32.3 | 1912 |
| shooting inexistant (ensemble vide) | 21.4 | 15.7 | 0 |
| combinaison la plus large | 44.0 | 38.4 | 0 |

## Méthode

- Jeu de démo régénéré (`reset=True`) juste avant la mesure — chiffres reproductibles en rejouant `uv run pytest tests/search/test_perf.py -q`.
- 20 requêtes représentatives de l'usage réel de `/search` : parcours sans filtre, une facette, plusieurs facettes combinées, plein texte français, plages ISO/focale, pagination par curseur, ensemble vide, combinaison la plus large.
- Le « round-trip » mesure le temps client complet (FastAPI `TestClient`, base Postgres locale) ; `took_ms` est la mesure serveur exposée dans le contrat (`SearchResponse.took_ms`), affichée telle quelle dans l'UI (§3-K.2).
- Environnement de mesure : base de test locale (`apex_test`, PostgreSQL 18, conteneur Docker), pas d'environnement de production — les temps réels côté Neon/Vercel restent à mesurer au premier déploiement (§ risques du plan, R4/R5).
