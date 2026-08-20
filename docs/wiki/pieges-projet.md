---
type: pieges
maj: 2026-08-20
---

# Pièges spécifiques à ce projet

Pièges constatés en conditions réelles sur Apex. Les pièges valables sur **n'importe quel**
projet de la même stack vivent dans la skill globale `stack-pitfalls`, pas ici.

- **Un lot d'upload reste bloqué en `processing` indéfiniment, `done: false` malgré
  `progress: 1.0` et une file vide** — la base de développement n'avait jamais été recréée
  après une édition **en place** de `0001_schema_initial.py` : elle portait encore l'ancien
  prédicat de `job_dedupe_idx`, tandis que le code et `apex_test` portaient le nouveau. La
  convention « migration unique, environnement jetable » implique que toute édition en place
  d'une révision **oblige** à recréer les bases existantes → `DROP SCHEMA public CASCADE` +
  `CREATE SCHEMA public` + `alembic upgrade head` sur chaque base, dev comprise. *(2026-08-20)*

- **Une fixture de test dont l'EXIF est construit avec le fuseau local de la machine
  (`datetime.now(UTC).astimezone().replace(tzinfo=None)`) fait tomber `shot_at` hors de la
  fenêtre du shooting** — `pipeline/exif.py::compute_shot_at` interprète l'EXIF naïf avec le
  fuseau du **boîtier** (`Europe/Paris` par défaut), pas celui de la machine de test. Effets en
  cascade : `no_matching_window`, `shooting_id` reste `NULL`, et `regroup_bursts_for_shooting`
  — filtré par `shooting_id` — ne forme donc **aucune** série. → Fixer explicitement
  `ZoneInfo("Europe/Paris")` dans toute fixture qui fabrique un horodatage EXIF, comme le fait
  `test_ingest_e2e.py` (`shooting_ctx["midpoint_paris"]`). *(2026-08-20)*

- **Une fiche de quarantaine affiche un code technique brut (`shot_at_exif : 1998-01-01T…`) au
  lieu d'un libellé français** — les dictionnaires de traduction du frontend
  (`QuarantineCard.DETAIL_LABELS`, `labels.ts::UNATTACHED_REASON_LABELS`) sont maintenus à la
  main et se désynchronisent des clés réellement émises par le pipeline. Trois occurrences en
  J1, dont une causée par un motif (`exif_inconsistent`) devenu réellement atteignable *après*
  la dernière mise à jour du dictionnaire. → Dériver ces dictionnaires du type généré depuis
  l'OpenAPI (les énumérations sont désormais fermées dans le contrat) plutôt que de les
  recopier, et conserver le test de correspondance exhaustive dans les deux sens. *(2026-08-20)*

- **`PATCH /cameras/{id}` avec `timezone: ""` cassait toute ingestion ultérieure du boîtier** —
  `ZoneInfo("")` lève `ValueError`, pas `ZoneInfoNotFoundError` ; l'exception échappait au
  `except` du pipeline, le job mourait par épuisement des tentatives et le média restait hors de
  tout bac. → Valider le fuseau au schéma d'entrée (`CameraPatch`) **et** capturer `ValueError`
  en défense en profondeur. *(2026-08-20)*

- **`GET /media` exclut les doublons exacts par défaut, volontairement** (critère « une rafale
  n'affiche qu'un représentant »). Un doublon n'est donc listable qu'avec `duplicates=true`, et
  une série ne se replie qu'avec `series=collapsed`. Tout nouvel écran qui doit voir ces médias
  passe par un **paramètre explicite** ; ne jamais reconstituer la liste côté client par des
  `GET /media/{id}` en N+1. *(2026-08-20)*

- **Le cloisonnement du parc de boîtiers est plus large que la matrice des rôles ne le laisse
  croire** : un photographe voit et peut muter un boîtier dès qu'il apparaît dans **ses propres**
  médias, même sans affectation formelle par le dirigeant. Choix délibéré — sans lui, le critère
  « un décalage d'horloge corrige rétroactivement le rattachement » est indémontrable pour un
  boîtier découvert automatiquement à l'ingestion (`owner_user_id IS NULL`). Restreindre à
  l'égalité stricte `owner_user_id == user.id` est un changement d'une ligne dans
  `services/access.py`, à décider en revue produit. *(2026-08-20)*
