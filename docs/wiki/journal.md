---
type: journal
maj: 2026-08-20
---

# Journal des runs

## 2026-08-20 — J1, socle et ingestion (`feature/socle-ingestion`)
Livré : modèle de données complet des 3 jalons (28 tables, une seule révision Alembic),
authentification à deux rôles cloisonnés, CRUD référentiel et shootings, upload par lot avec
reprise, file de tâches en table PostgreSQL, pipeline d'ingestion (EXIF, rattachement temporel,
dédoublonnage exact et perceptuel, intégrité, quarantaine motivée) et 14 écrans.
Le fait notable : la revue a trouvé 7 bloquants, dont **quatre dans la file de tâches et aucun
dans le pipeline** — le maillon faible de « aucun fichier perdu » est la file, pas l'ingestion.
Deuxième fait notable : la même régression de libellé est revenue trois fois, jusqu'à ce que les
énumérations soient fermées dans le contrat OpenAPI plutôt que maintenues à la main.
Blackboard d'origine : `.agent-team/` (éphémère).
Détail : `architecture.md#non-double-traitement--réclamation-atomique-et-verrou-logique` et
`architecture.md#contrat-dapi-gelé-dans-openapijson-et-régénéré`.
