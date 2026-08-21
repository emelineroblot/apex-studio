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

- **`requires-python = ">=3.13"` était présent depuis le tout premier commit alors que le plan
  avait décidé Python 3.12 (§3-B)** — deux jalons et plusieurs revues n'ont rien vu, parce que
  rien n'installait jamais le projet comme le ferait la production. `rapidocr-onnxruntime`
  (moteur OCR) n'a **jamais** publié de version compatible Python 3.13 (vérifié sur toutes ses
  versions via l'API PyPI) ; `uv sync` en local l'installe quand même sur Python 3.13.5, sans
  avertissement, alors que `pip` (utilisé par le builder Vercel) refuse purement et simplement
  de le résoudre. → `uv run`/`uv sync` valident un environnement de **développement**, jamais
  une installation de **production** ; `bash scripts/check_prod_install.sh` (nouveau, conteneur
  Linux jetable, `pip` réel) est désormais le seul test qui fait foi avant un déploiement. Voir
  `docs/wiki/architecture.md`, « Version Python figée à 3.12 ». *(2026-08-21)*

- **Toute édition simultanée de `pyproject.toml`/`requires-python` (borne haute) ou de
  `.python-version` alors qu'un `.venv` partagé est actif force sa reconstruction au **prochain**
  `uv run`/`uv sync` — y compris ceux lancés par un autre agent, silencieusement.** Reproduit en
  conditions réelles (bac à sable) : `uv run python --version` supprime et recrée `.venv` dès que
  la version épinglée (`.python-version`) ou que la borne haute de `requires-python` exclut
  l'interpréteur actif — même sans qu'aucun `uv sync` explicite n'ait été lancé. À l'inverse,
  **élargir uniquement le plancher** (`>=3.12` sans borne haute, l'interpréteur actif restant
  valide) ne touche pas au `.venv` : c'est la seule forme de changement de version sûre à côté
  d'un agent qui travaille en parallèle. `uv lock`/`uv export`, eux, n'écrivent que le lockfile
  et ne touchent jamais `.venv`, quel que soit l'écart avec `pyproject.toml` — d'où la stratégie
  retenue : préparer/valider la version resserrée dans une copie isolée, ne l'appliquer au dépôt
  réel qu'une fois le `.venv` partagé libre. *(2026-08-21)*

- **`requirements.txt` généré par `uv export --no-dev --format requirements-txt` casse
  l'installation `pip` de deux façons indépendantes**, sans lien avec la question du poids :
  (1) sans `--no-emit-project`, la ligne `-e .` du paquet local n'a pas de hachage, ce qui casse
  le mode empreintes de `pip` dès qu'une autre ligne (n'importe laquelle) porte un hachage — le
  paquet local doit être exclu de l'export et installé à part (`pip install --no-deps -e .`).
  (2) Le message de statut `uv` (`Resolved N packages…`) part normalement sur stderr avec une
  redirection `>` correcte — mais un fichier historique du dépôt le portait quand même en ligne
  1, rendant `pip install -r requirements.txt` invalide dès le départ (`Invalid requirement`).
  Toujours vérifier la première ligne du fichier généré. *(2026-08-21)*

- **`opencv-python-headless` ne réduit le poids que d'environ 35 Mo sur ce projet, pas des
  « 185 Mo » qu'on pourrait attendre d'après le poids d'`opencv_python.libs` seul** — le module
  compilé `cv2` lui-même (~72 Mo) est quasi identique entre les deux variantes ; seule la
  bibliothèque `.libs` (GTK/Qt) rétrécit (116 Mo → 81 Mo). Ne pas construire un budget de poids
  sur cette seule substitution sans avoir mesuré. Substitution non triviale à effectuer via
  `uv`/`pip` : `[tool.uv.override-dependencies]` ne fait que réviser une contrainte de version
  pour un paquet déjà nommé dans le graphe, **jamais** remplacer un nom de paquet par un autre
  (testé, confirmé sans effet sur la résolution) — la seule méthode fiable est
  `pip uninstall opencv-python` puis `pip install --no-deps opencv-python-headless==<même
  version exacte>`, jamais une simple installation par-dessus (laisserait les bibliothèques GUI
  orphelines sur le disque). *(2026-08-21)*

- **`tests/conftest.py` porte un fixture `session, autouse=True` qui recrée le schéma Postgres
  et fait tourner Alembic pour n'importe quel test collecté** — y compris `tests/ocr/test_eval.py`,
  dont la docstring promet pourtant « aucune base de données ». La promesse porte sur la
  *logique* du test, pas sur la collecte pytest globale. Pour rejouer ce test isolément (hors du
  `docker compose` du dépôt, sans risquer d'interbloquer un `pytest` déjà en cours ailleurs — voir
  plus haut « ne jamais lancer deux pytest concurrents »), démarrer un Postgres jetable
  **séparé** qui écoute directement sur le port `55433` (`postgres:18-alpine … -p 55433`) et
  partager son *network namespace* avec le conteneur de test (`docker run --network
  container:<db>`) plutôt que de publier un port hôte — `TEST_DATABASE_URL` est une chaîne
  **littérale** (`localhost:55433`) dans `conftest.py`, pas dérivée de `DATABASE_URL`. *(2026-08-21)*

- **`tests/pipeline/test_quarantine_and_listing.py::test_default_list_shows_only_one_item_per_burst_series`
  construit son horodatage EXIF avec `.astimezone().replace(tzinfo=None)` — fuseau de la
  machine, pas `Europe/Paris`** — reproduction du piège déjà documenté ci-dessus pour
  `test_ingest_e2e.py`, mais dans un fichier qui n'a pas reçu le même correctif. Passe par
  coïncidence sur une machine réglée sur `Europe/Paris` (le cas probable du poste de
  développement d'origine), échoue de façon **reproductible** (pas flaky) dans tout conteneur en
  UTC — donc dans à peu près n'importe quel CI ou environnement de vérification indépendant.
  Constaté en vérifiant l'installation de production dans un conteneur Linux, sans lien avec
  cette vérification elle-même. **Corrigé le 2026-08-21** (`astimezone(PARIS)`, constante
  `PARIS = ZoneInfo("Europe/Paris")` en tête de fichier, comme `test_ingest_e2e.py`) et vérifié
  dans les deux sens : `TZ=UTC0 uv run pytest …` échoue sans le correctif, passe avec.
  **`TZ=UTC0` fonctionne sur Windows** (le CRT le lit au démarrage du processus) alors que
  `time.tzset()` n'y existe pas : rejouer un test suspect de dépendre du fuseau ne demande donc
  aucun conteneur. *(2026-08-21)*

- **Sous `set -euo pipefail`, une affectation `VAR=$(cmd | awk …)` dont `cmd` échoue tue le
  script entier, silencieusement si `cmd` est muselée par `2>/dev/null`.** Vécu sur
  `scripts/check_prod_install.sh` : le `pip show opencv-python` de la substitution headless
  réussissait tant que le moteur OCR était une dépendance principale ; le jour où il est passé
  en extra optionnel — c'est-à-dire le jour même où le script devenait le garde-fou obligatoire
  avant déploiement — la même ligne s'est mise à échouer et le script s'arrêtait juste après
  avoir affiché « [2/4] », sans un mot, code de sortie 1. Diagnostiqué comme une panne
  d'installation pendant plusieurs minutes. → `|| true` sur toute substitution dont l'échec est
  un cas nominal ; et surtout : **un garde-fou doit être rejoué après le changement qu'il est
  censé garder**, il fait partie du périmètre de ce changement, pas de son décor. *(2026-08-21)*

- **Un test qui fabrique ses propres données ne teste pas les données de la démonstration.**
  Les 303 tests backend passaient, et pourtant aucune collection du jeu de démo n'était
  livrable : le générateur ne posait pas de `storage_key_hd`, quand chaque test, lui, en
  fabriquait un. Rejouer le parcours réel (`scripts/verify_j3_flow.py`) l'a montré en une
  minute. À faire à chaque jalon, avant de conclure. *(2026-08-21)*

- **Un chiffre affiché sous le même nom à deux endroits doit venir du même calcul.** Le
  tableau de bord J3 recalculait « le taux de rattachement automatique » en SQL, à côté de
  `/stats/auto-attach-rate` qui le calculait déjà — et la définition est peu intuitive (un
  média rattaché par l'OCR mais arbitré par un humain ne compte pas comme automatique, les
  doublons sont exclus). Deux versions auraient produit deux nombres différents sous le même
  libellé, sans que personne sache lequel croire. Le dashboard **réutilise** désormais la
  fonction existante, au prix d'une requête de plus. *(2026-08-21)*

- **`npx tsc --noEmit | tail -2` renvoie le code de sortie de `tail`, jamais celui de
  `tsc`.** Un `&&` derrière un tube ne garantit donc rien : un commit est parti avec un
  typecheck rouge. Vérifier le code de sortie explicitement (`npx tsc --noEmit; echo $?`) ou
  ne pas rediriger. Vaut pour toute commande de vérification enchaînée derrière un tube.
  *(2026-08-21)*

- **La police par défaut de Pillow ne couvre que l'ASCII.** `ImageFont.load_default()` —
  utilisée dès que `DejaVuSans-Bold.ttf` est introuvable, ce qui est le cas sur Windows et
  sur toute image Linux sans polices système — dessine un caractère manquant (▯) pour tout
  accent et tout tiret cadratin. Invisible en test (aucun test ne regarde les pixels d'un
  filigrane), visible sur la première vraie image rendue. Les textes dessinés dans une image
  sont translittérés en ASCII. *(2026-08-21)*

- **`require_owner` ne protège aucune route destructrice de ce projet, tant que
  `GET /demo/accounts` est public** — l'endpoint de self-service de la démo renvoie les
  identifiants en clair, par conception. Le cloisonnement de `POST /demo/seed?reset=true`
  (`TRUNCATE` de 25 tables) se résumait donc à trois appels : lire les identifiants, se
  connecter, détruire. → Toute route destructrice se protège par un **secret serveur jamais
  publié** (`X-Worker-Secret`, même patron que `POST /jobs/tick`), pas par un rôle ; et son
  travail sort de la requête (`202 {job_id}` + enqueue) plutôt que de drainer 60 s de façon
  synchrone sur un pool de 2+3 connexions. **À rappeler au J3** : la réinitialisation nocturne
  et la livraison ZIP relèvent exactement du même patron. *(2026-08-21)*
