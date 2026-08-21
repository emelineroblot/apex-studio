---
type: pieges
maj: 2026-08-21
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

- **`sqlalchemy.text()` n'associe jamais `:nom` à un bind param quand il est immédiatement
  suivi d'un second `:`** (regex de reconnaissance, exclusion volontaire pour ne pas capturer
  l'opérateur de cast Postgres `::` collé à une colonne). `WHERE (:media_ids::bigint[] IS NULL
  …)` part donc tel quel vers Postgres — `SyntaxError`, reproduit en conditions réelles dans
  `services/search_projection.py`. → Toujours un **espace** avant `::` sur un paramètre nommé
  (`:media_ids ::bigint[]`) ; `valeur ::type` reste un cast Postgres valide avec un espace.
  Piège symétrique : un commentaire SQL `-- ... :mot ...` **à l'intérieur** d'un `text(...)`
  est scanné par le même regex — une phrase de documentation citant `:nom` comme exemple générique
  a fait échouer l'exécution (`A value is required for bind parameter`) avant d'être déplacée en
  commentaire Python, hors de la chaîne SQL. *(2026-08-21)*

- **`insert(Model)`/`update(Model)` (classe ORM) coûtent jusqu'à ~45× plus cher que
  `insert(Model.__table__)`/`update(Model.__table__)` (Core pur) dès que l'identity map de la
  session porte déjà beaucoup d'objets** (constaté avec quelques milliers de `Media`/
  `MediaSeries` déjà chargés) — 4,6 s contre 0,07 s par lot de 500 lignes sur
  `media_engagement` dans `apex/demo/seed.py` (`cProfile`, dominé par l'attente réseau, aucune
  relation ORM pourtant définie sur ces modèles). → Pour toute écriture en lot sur une session
  qui a déjà accumulé beaucoup d'objets (générateurs, imports), passer par `Model.__table__`
  systématiquement, pas seulement « si ça semble lent ». Voir `docs/wiki/architecture.md`,
  section générateur de démo, pour le détail chiffré. *(2026-08-21)*

- **`func.unnest(colonne).table_valued("v", joins_implicitly=True)` sans `.render_derived()`
  référence une colonne `anon_1.v` que Postgres ne connaît pas** — SQLAlchemy rend
  `unnest(...) AS anon_1` (sans liste de colonnes dérivées) tout en générant `SELECT anon_1.v`
  dans la requête, provoquant `UndefinedColumn: anon_1.v` (reproduit en conditions réelles dans
  `services/facets.py`, facettes tableau team/driver/car_number). → Toujours chaîner
  `.render_derived()`, qui force le rendu `AS anon_1(v)`. *(2026-08-21)*

- **La liste `TRUNCATE` du plan (§3-N.2, réinitialisation du jeu de démo) omet la table
  `circuit`** — un second `reset=True` échoue en `UniqueViolation` sur `circuit.name`, les 8
  circuits réels du catalogue n'étant jamais effacés (reproduit en conditions réelles,
  `tests/demo/test_seed.py::TestDeterminism`). → Corrigé dans
  `apex/demo/seed.py::_RESET_TABLES` (ajout de `circuit`) ; à vérifier une nouvelle fois si une
  future table de référence rejoint le catalogue du jeu de démo. *(2026-08-21)*

- **`require_owner` ne protège aucune route destructrice de ce projet, tant que
  `GET /demo/accounts` est public** — l'endpoint de self-service de la démo renvoie les
  identifiants en clair, par conception. Le cloisonnement de `POST /demo/seed?reset=true`
  (`TRUNCATE` de 25 tables) se résumait donc à trois appels : lire les identifiants, se
  connecter, détruire. → Toute route destructrice se protège par un **secret serveur jamais
  publié** (`X-Worker-Secret`, même patron que `POST /jobs/tick`), pas par un rôle ; et son
  travail sort de la requête (`202 {job_id}` + enqueue) plutôt que de drainer 60 s de façon
  synchrone sur un pool de 2+3 connexions. **À rappeler au J3** : la réinitialisation nocturne
  et la livraison ZIP relèvent exactement du même patron. *(2026-08-21)*
