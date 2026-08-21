---
type: architecture
maj: 2026-08-21
---

# Décisions d'architecture

## File de tâches en table PostgreSQL et worker « tiré »
*Décidé le 2026-08-20 — run `J1 socle et ingestion`*

**Décision.** Le traitement asynchrone repose sur une table `job` drainée par
`FOR UPDATE SKIP LOCKED`, sans Celery ni Redis. Le worker n'est pas un processus permanent :
un unique module `apex/queue/runner.py::drain(worker_id, deadline)` est piloté par deux
entrées — `apex.cli worker --loop` en local, `POST /jobs/tick` (budget 250 s) en serverless.
Le tick est déclenché par les enqueues de l'API, par le polling de l'UI pendant un upload et
par le cron nocturne.

**Pourquoi.** Deux contraintes d'hébergement se cumulent. Vercel Hobby ne peut pas héberger
un processus long : les fonctions plafonnent à 300 s et les crons Hobby sont limités à une
exécution par jour de 10 s maximum. Et le quota Neon (100 CU-h/mois) serait brûlé en environ
deux semaines par un worker qui pollerait 24/7, puisqu'il tiendrait le compute éveillé en
permanence. Les alternatives écartées : un worker conteneurisé sur Fly.io/Koyeb (ajoute un
hébergeur hors stack et ne règle pas le quota Neon) et le traitement synchrone dans la
requête d'upload (viole le critère « traité en tâche de fond sans bloquer l'interface »).

**Conséquences.** Rien n'est traité si personne ne sollicite l'application — sans effet ici,
l'upload par les visiteurs étant hors périmètre. `drain()` ne contient aucune boucle : le
sommeil à vide vit dans le pilote CLI, jamais dans `drain()`. Si le comportement en ligne
s'avérait insuffisant, l'arbitrage vers un worker externe doit être explicite, jamais
silencieux.

## Non-double-traitement : réclamation atomique et verrou logique
*Décidé le 2026-08-20 — run `J1 socle et ingestion`*

**Décision.** La réclamation est une seule requête atomique (`WITH claimed AS (SELECT …
FOR UPDATE SKIP LOCKED) UPDATE job …`) suivie d'un commit immédiat. Le traitement se fait
**hors** de la transaction du verrou ; c'est ensuite `status='running' AND locked_by=<moi>`
qui joue le rôle de verrou logique. Trois garanties se superposent : `SKIP LOCKED`, l'index
unique partiel `(kind, dedupe_key)` sur les jobs vivants, et des transitions gardées par
`WHERE id = :id AND locked_by = :worker_id` avec contrôle du `rowcount`.

**Pourquoi.** Traiter à l'intérieur de la transaction du verrou tiendrait un verrou de ligne
pendant plusieurs secondes : transactions longues, connexions bloquées (le pool est
volontairement petit, `pool_size=2, max_overflow=3`, contrainte serverless) et aucune
visibilité de l'état « en cours » pour l'UI de suivi de lot. Le prix à payer est un mécanisme
explicite de récupération des jobs abandonnés : `reap_stale` repasse en `pending` tout job
`running` sans `heartbeat_at` depuis 3 minutes. Le seuil est **volontairement inférieur** au
`maxDuration` de 300 s : c'est le heartbeat, rafraîchi avant chaque job, qui distingue un job
vivant d'un job mort, pas la durée écoulée.

**Conséquences.** Deux règles non négociables, toutes deux issues de bugs réels de la revue
J1 : **une réclamation sans exécution ne doit jamais consommer une tentative** (au deadline,
`drain()` relâche les jobs réclamés non traités — sinon trois cycles de polling normal
suffisaient à envoyer des photos valides en quarantaine), et **un passage à `dead` doit
toujours produire un effet métier lisible** (`on_dead` est dispatché sur les deux chemins :
épuisement des tentatives *et* `reap_stale`). Le `worker_id` doit être unique par
processus/requête, sinon la garde `locked_by` ne distingue rien.

## Horodatage des photos : `shot_at_exif` naïf, `shot_at` calculé
*Décidé le 2026-08-20 — run `J1 socle et ingestion`*

**Décision.** Deux colonnes distinctes. `shot_at_exif TIMESTAMP` conserve la valeur EXIF
brute, **naïve**, telle que lue dans le fichier. `shot_at TIMESTAMPTZ` est dérivée :
`localize(shot_at_exif, camera.timezone) + camera.clock_offset_seconds`. Le rattachement au
shooting compare `shooting.period @> media.shot_at`, donc des instants, jamais des textes.

**Pourquoi.** L'EXIF `DateTimeOriginal` est sans fuseau par nature. Écraser la valeur lue par
une valeur convertie rendrait tout recalcul impossible : régler un décalage d'horloge après
coup ne pourrait alors que s'appliquer à la valeur déjà corrigée, avec une **dérive
cumulative** à chaque nouveau réglage. En gardant la source brute, `reattach_camera` recalcule
toujours depuis l'origine — régler deux fois de suite produit exactement `offset2 - offset1`,
et revenir au premier réglage reproduit le `shot_at` initial bit à bit (vérifié par test, avec
cycle rouge/vert).

**Conséquences.** Toute lecture métier de la date de prise de vue passe par `shot_at`, jamais
par `shot_at_exif` — qui n'est que la trace d'origine et un champ de diagnostic. Toute
modification de `camera.timezone` **ou** de `camera.clock_offset_seconds` doit enqueuer
`reattach_camera` : traiter seulement le décalage laisse les médias existants dans l'ancien
fuseau. Le job trace dans son `result` le nombre de médias re-rattachés, chiffre exposé par
`CameraPatchResponse.reattached` — c'est ce qui rend le critère d'acceptation démontrable.

## Deux axes d'état orthogonaux pour un média
*Décidé le 2026-08-20 — run `J1 socle et ingestion`*

**Décision.** `media` porte deux colonnes d'état indépendantes : `ingest_status`
(`uploaded → processing → ingested`, ou `quarantined`, terminal) et `attachment_status`
(`unattached`, `shooting_attached`, `engagement_attached`, puis `pending_review` et
`inconsistent` en J2). Deux `CHECK` en base :
`ingest_status <> 'quarantined' OR quarantine_reason IS NOT NULL` et
`attachment_status <> 'shooting_attached' OR shooting_id IS NOT NULL`.

**Pourquoi.** Un champ d'état unique mélangerait la santé du **fichier** et l'avancement du
**rattachement**, qui ne sont pas la même question : un média correctement ingéré peut être un
doublon, un média en quarantaine n'a aucun statut de rattachement pertinent. Le `CHECK` de
motif obligatoire rend structurellement impossible une quarantaine sans explication — c'est le
niveau de garantie qu'exige l'invariant « jamais de rejet silencieux », qu'une simple
discipline applicative ne tiendrait pas.

**Conséquences.** Les bacs de l'UI sont des requêtes, pas des états : « à rattacher » =
`ingested AND unattached`, « quarantaine » = `quarantined`. Les motifs de quarantaine (10) et
de non-rattachement (3) sont des **énumérations fermées**, verrouillées par test contre le
contrat OpenAPI — voir « Contrat d'API » ci-dessous.

## Chaîne « aucun fichier n'est jamais perdu silencieusement »
*Décidé le 2026-08-20 — run `J1 socle et ingestion`*

**Décision.** L'invariant central du projet n'est pas une intention, c'est une chaîne de sept
mécanismes : (1) enqueue transactionnel — la ligne `media` et son job `ingest_media` sont
insérés dans **une seule** transaction, il est impossible d'avoir un média sans job ;
(2) idempotence de l'upload par en-tête `Idempotency-Key` (UUID stable par fichier, conservé
côté navigateur), un rejeu renvoie le même `media_id` ; (3) **aucune suppression, jamais** —
un doublon reçoit `duplicate_of_media_id`, un fichier corrompu passe en `quarantined`, il
n'existe aucun `DELETE` sur `media` dans le code applicatif (seul `demo_reset` truncate) ;
(4) `CHECK` de motif obligatoire ; (5) réconciliation de lot sur `expected_count` annoncé par
le navigateur ; (6) `sweep_orphans`, qui transforme un objet de stockage sans ligne en base en
média quarantiné `orphan_object` plutôt que de l'effacer ; (7) un `pipeline_event` par étape,
lisible dans l'UI.

**Pourquoi.** C'est le critère d'acceptation le plus difficile à tenir, parce qu'il se viole
toujours par un chemin d'échec qu'on n'a pas pensé, pas par une décision explicite. Chaque
garantie ferme une classe de perte différente : perte à l'écriture (1), perte à la reprise (2),
perte par nettoyage (3), perte par ignorance (4), perte en amont de l'API (5, 6), perte de
traçabilité (7). Aucune ne remplace les autres.

**Conséquences.** Toute évolution du pipeline doit se relire contre ces sept points. La revue
J1 a montré que deux chemins d'échec silencieux avaient malgré tout survécu — un job mort sans
`on_dead`, et des jobs réclamés puis abandonnés — tous deux à l'intérieur de la file, pas dans
le pipeline. **Le maillon faible de cette chaîne est la file, pas l'ingestion.** Corollaire :
préférer un bac visible à un octet perdu, y compris quand la cause est une panne
d'infrastructure.

## Dédoublonnage : hash exact et hash perceptuel
*Décidé le 2026-08-20 — run `J1 socle et ingestion`*

**Décision.** Hash exact en **BLAKE2b-256** (stdlib, calculé en flux par blocs de 1 Mo),
stocké en `BYTEA(32)`, indexé mais **non contraint en unique** — deux médias peuvent partager
un hash, le second est marqué doublon. Hash perceptuel en **pHash DCT écrit à la main en
numpy** (~40 lignes), 64 bits stockés en `BIGINT`, calculé sur la vignette 320 px. Rafales
regroupées par balayage linéaire par `(shooting, boîtier)` trié sur `shot_at`, nouvelle série
dès que `gap > burst_gap_seconds` ou `hamming > phash_max_distance` (paramètres en
`app_setting`, défauts 2,0 s et 10). Représentant = netteté maximale (variance de Laplacien).

**Pourquoi.** MD5 est écarté par principe (signal négatif en revue), SHA-256 est ~2× plus lent
que BLAKE2b en CPython pour aucun gain ici. Le refus d'`imagehash` est une contrainte
d'hébergement, pas une préférence : il tire `scipy` (~40 Mo de wheel) uniquement pour une DCT,
face au plafond de **250 Mo décompressés** d'une fonction Vercel Python déjà entamé par
`numpy`, `Pillow` et, en J2, `onnxruntime`. dHash aurait coûté 10 lignes mais résiste mal au
flou de bougé, omniprésent en sport mécanique. Le clustering global (BK-tree, DBSCAN) est de la
sur-ingénierie : une rafale est un phénomène temporel local, pas un cluster global.

**Conséquences.** Le hash exact sert **deux fois** : détection de doublon et clé de stockage
content-addressed — deux fichiers identiques n'occupent qu'un objet. Le choix du représentant
est déterministe (égalités tranchées par `shot_at` puis `id`), donc reproductible après un
`demo_reset`. Les doublons sont exclus par défaut de `GET /media` et ne se listent qu'avec
`duplicates=true` ; les séries se replient avec `series=collapsed`.

## Stockage objet médié par le backend, clés content-addressed
*Décidé le 2026-08-20 — run `J1 socle et ingestion`*

**Décision.** Cloudflare R2 en juridiction `eu`, accédé uniquement par `boto3`. **Aucune URL
présignée n'est jamais émise** : un seul endpoint, `GET /media/{id}/file/{variant}` avec
`variant ∈ {thumb, preview, hd}`, authentifié, cloisonné, streamé par chunks de 64 Ko, avec
`ETag: "{hash}"` et gestion du `If-None-Match` → `304`. Clés content-addressed
(`hd/{h[0:2]}/{h}.jpg`, `preview/…webp`, `thumb/…webp`). Le filigrane est **cuit dans les
pixels** à l'ingestion, par Pillow, jamais posé en overlay CSS.

**Pourquoi.** L'égress gratuit de R2 est déterminant puisque le backend médie 100 % des accès :
chaque aperçu affiché est un transfert sortant. B2 plafonne l'égress gratuit à 3× le stockage
moyen, franchissable dès que la démo tourne. Le refus des URL présignées est un invariant
produit : la variante `hd` doit rester refusée tant qu'une sélection n'est pas validée, et une
URL présignée devinée ou partagée contournerait ce contrôle. Le filigrane cuit résiste au clic
droit ; un overlay CSS non — et ce point est démontrable en direct pendant la démo.

**Conséquences.** Le content-addressing rend l'ingestion idempotente gratuitement (réécrire un
dérivé écrase le même octet) et fait porter au cache navigateur tout le poids d'une grille de
plusieurs milliers d'items. En contrepartie, toute la bande passante média passe par Vercel
(100 Go/mois en Hobby) : c'est la métrique à surveiller en premier. Le quota par shooting
(`quota_bytes`, 2 Go par défaut) est vérifié **avant** chaque `PUT` et un dépassement produit
un `413` **plus** un média quarantiné `quota_exceeded` — jamais un rejet muet.

## Authentification, cloisonnement et garde-fou de secrets
*Décidé le 2026-08-20 — run `J1 socle et ingestion`*

**Décision.** JWT HS256 en en-tête `Authorization` (TTL 8 h en interne, 30 min pour la future
session client), mots de passe en bcrypt. Le cloisonnement passe par **une porte unique**,
`apex/services/access.py`, qui expose `visible_shooting_ids(user) -> Select` (une sous-requête
SQL, pas une liste Python) et `assert_can_read_media(...)` ; tous les repositories l'empruntent.
Une ressource hors périmètre renvoie **`404`, jamais `403`**. `APP_ENV` vaut `production` par
défaut et l'application **refuse de démarrer** si un secret a encore sa valeur du dépôt.

**Pourquoi.** Le cookie `HttpOnly` protégerait mieux du XSS mais impose `SameSite=None; Secure`
plus CORS avec credentials entre deux domaines Vercel, et se marie mal avec le lien client de
J3 ; le JWT couvre les trois portées (dirigeant, photographe, client) avec un seul mécanisme et
se documente nativement dans l'OpenAPI. Le risque XSS est **accepté et documenté** : données
fictives, réinitialisées chaque nuit. Le `404` au lieu du `403` évite de révéler l'existence
d'une ressource. Le défaut `production` d'`APP_ENV` corrige une première version *fail-open* du
garde-fou : avec `local` par défaut, il ne protégeait que les déploiements où `APP_ENV` avait
été explicitement posé, c'est-à-dire jamais dans le scénario visé — la variable oubliée.

**Conséquences.** Un endpoint ajouté sans passer par `access.py` est un trou, et la revue J1 en
a trouvé un (`PATCH /cameras/{id}`, qui permettait de détacher en masse les photos d'un autre
photographe). Le test paramétré qui parcourt les routes de l'OpenAPI est volontairement scopé
aux préfixes J1 réellement implémentés : **il faut l'élargir à chaque routeur J2/J3 câblé**,
sinon il donne une fausse assurance. Écart assumé au plan : `passlib` a été retiré au profit
d'un appel direct à `bcrypt` (incompatibilité reproductible avec `bcrypt` 5.0.0) — l'algorithme
est inchangé, seule la couche d'indirection disparaît.

## Contrat d'API gelé dans `openapi.json` et régénéré
*Décidé le 2026-08-20 — run `J1 socle et ingestion`*

**Décision.** `services/api/openapi.json` est committé et fait foi. Le frontend n'écrit **jamais**
un type d'API à la main : `npm run gen:api` régénère `apps/web/src/lib/api/schema.d.ts` via
`openapi-typescript`. Tout ensemble fermé côté modèle (motifs de quarantaine, motifs de
non-rattachement, clés de `quarantine_detail`) est exposé au contrat comme une vraie énumération
ou un schéma fermé, et `tests/test_openapi_contract.py` échoue si les valeurs divergent des
tuples de `apex/models/media.py` — **dans les deux sens** (motif manquant *et* motif fantôme).

**Pourquoi.** Backend et frontend ont été menés en parallèle : cinq divergences de forme sont
apparues dès la première intégration réelle, dont un double préfixe `/api/v1` qui cassait 100 %
des vignettes. Et la même régression « libellé français manquant » est revenue **trois fois**,
toujours par le même mécanisme : un ensemble fermé côté modèle exposé en `str`/`dict` libre au
contrat, donc un typage généré qui ne protège plus rien et un dictionnaire de traduction
maintenu à la main. Fermer l'énumération dans le contrat transforme l'oubli en erreur de
compilation. `quarantine_detail` est modélisé en objet à propriétés **optionnelles** avec
`extra="ignore"` : sa forme varie légitimement par motif, un schéma à champs requis serait un
contrat mensonger, et une 18ᵉ clé de diagnostic ne doit jamais faire échouer un `GET /media/{id}`
en production — c'est au test de la détecter, pas à un `500`.

**Conséquences.** Toute évolution de schéma backend impose : régénérer `openapi.json`, puis
`npm run gen:api`. Un frontend qui code contre un contrat périmé compile parfaitement et casse
en production. Le contrôle CI qui régénère et fait `git diff --exit-code` reste **à livrer** —
il était prévu au plan (§3-A.3) et n'existe pas encore ; livré après coup, il ne sert qu'à
constater les dégâts.

## Immuabilité de la facture émise : un trigger, pas une règle applicative
*Décidé le 2026-08-20 — run `J1 socle et ingestion`* (schéma livré en J1, usage en J3)

**Décision.** `invoice_line` porte un **snapshot** (libellé, quantité, prix unitaire) sans clé
étrangère vivante vers `media`. Tant que `invoice.status='draft'`, `refresh_draft_invoice`
remplace les lignes à chaque changement de sélection validée ; à l'émission, on fige. La
garantie est portée par deux triggers PL/pgSQL : `invoice_line_immutable_trg` (BEFORE
INSERT/UPDATE/DELETE) et `invoice_immutable_fields_trg` (BEFORE UPDATE sur `invoice`, qui
interdit aussi le retour de `issued` vers `draft`).

**Pourquoi.** Des lignes référençant les médias par clé étrangère feraient changer le contenu
d'une facture émise dès que la sélection bouge : l'invariant est violé par construction. Une
garde purement applicative tient jusqu'à la première route qui l'oublie. C'est l'invariant
métier le plus fort du projet — il mérite une garantie qui ne dépende pas de la discipline du
code, et qui survive à un script de maintenance ou à une correction en base.

**Conséquences.** Le numéro de facture est consommé sur `invoice_number_seq` **uniquement à
l'émission** : une facture brouillon n'a pas de numéro. Ces triggers ne sortent pas de
l'autogenerate Alembic — ils sont écrits à la main dans `0001_schema_initial`, avec leur `DROP`
symétrique **en tête** du `downgrade()`. Tout test qui manipule une facture `issued` doit
s'attendre à une exception PL/pgSQL, pas à un refus applicatif.

## Base de données, migrations et stratégie de test
*Décidé le 2026-08-20 — run `J1 socle et ingestion`*

> **Révisé le 2026-08-21.** La base managée est **Supabase**, pas Neon — voir « Bascule vers
> Supabase » plus bas. Le reste de cette décision (une révision Alembic par jalon, base
> jetable) tient inchangé.

**Décision d'origine.** Neon (Francfort) pour la base managée. **Une seule révision Alembic par jalon**
(`0001_schema_initial` couvre les 28 tables des trois jalons) : tant qu'une révision n'est pas
mergée dans `main`, on l'édite en place au lieu d'en empiler une nouvelle. Les tests tournent
contre une vraie base PostgreSQL dédiée (`apex_test`), réinitialisée par `DROP SCHEMA` en
fixture session-scoped, chaque test dans une transaction annulée. Les tests de concurrence
utilisent de vrais **threads** avec des sessions distinctes. Aucun mock de base de données,
nulle part.

**Pourquoi.** Supabase a été écarté pour une raison unique mais rédhibitoire : mise en pause du
projet après 7 jours d'inactivité, mortel pour une démo consultée une fois par mois — le quota
de compute Neon est un risque moins grave, et il est neutralisé par le worker tiré (voir plus
haut). SQLite est exclu sans discussion : ni `tstzrange`, ni GiST, ni GIN, ni `tsvector`, ni
`SKIP LOCKED` — on testerait autre chose que ce qu'on livre. `testcontainers` a été écarté pour
son coût de démarrage sous Windows sur un projet de 8-12 jours, pas par principe.

**Conséquences.** L'environnement est **jetable** : si J2 ou J3 exige une refonte de schéma, on
repart d'une base vierge (`downgrade base` → `upgrade head` → `seed`) plutôt que d'empiler des
révisions. Corollaire à ne pas oublier : éditer la migration en place n'a **aucun effet** sur
une base déjà créée — voir `pieges-projet.md`. Et puisqu'il n'y a qu'une base de test, deux
`pytest` concurrents s'interbloquent sur le `DROP SCHEMA`.

## Projection de recherche `media_search` : réindexation synchrone, pas un job systématique
*Décidé le 2026-08-21 — run `J2 intelligence et recherche`*

**Décision.** `services/search_projection.py::project_media_search(session, media_ids)` est un
unique `INSERT … SELECT … ON CONFLICT (media_id) DO UPDATE`, appelé **directement et dans la
même transaction** à chaque endroit où `attachment_status`, un rattachement ou une série
changent (ingestion, OCR, reclassement, arbitrage humain, rattachement/retrait manuel, recalage
d'horloge). `media_ids=None` reconstruit la table entière — c'est le chemin qu'emprunte aussi le
générateur de démo, jamais un chemin de projection séparé. Le job `reindex_media` existe
(registre §3-E.3) mais n'est **pas** le mécanisme principal : c'est un point d'entrée
asynchrone secondaire, pour un déclenchement externe explicite.

**Pourquoi.** L'agent OCR avait laissé le constat en sortie de son lot : `reindex_media`
n'était câblé nulle part, `classify.project_media_batch` étant le seul endroit où l'OCR fait
bouger un `attachment_status`. Passer par la file à chaque changement (enqueue +
attente du prochain tick) aurait rendu la recherche périmée pendant la fenêtre entre l'action et
le drainage — inacceptable pour un critère d'acceptation qui promet une recherche
« utilisable », pas « éventuellement à jour ». La cohérence prime sur le découplage ici.

**Conséquences.** Toute nouvelle route ou tout nouveau handler qui touche
`attachment_status`/`media_engagement`/`is_series_representative` doit appeler
`search_projection` avant son `commit()`, sinon la recherche perd silencieusement le média —
« une projection périmée est un média introuvable » (formule reprise du constat de l'agent OCR).
`sweep_orphans` (J1) a été corrigé au passage : un objet orphelin devenait une ligne `media`
sans jamais rejoindre `media_search`.

## Recherche à facettes : neuf agrégats indexés plutôt qu'un `GROUPING SETS` fusionné
*Décidé le 2026-08-21 — run `J2 intelligence et recherche`*

**Décision.** Le compteur de chaque facette multi-sélection (§3-K.2, règle « sauf soi ») est
calculé par sa **propre** requête, filtrée par tous les prédicats actifs sauf le sien —
`services/facets.py`, 9 petits agrégats (6 scalaires, 3 tableaux via `unnest()`/
`table_valued(joins_implicitly=True)`) plutôt que le squelette `GROUPING SETS` esquissé au
plan.

**Pourquoi.** Le squelette du plan réutilise une seule CTE `filtered` (tous les filtres
appliqués) pour toutes les facettes via `GROUPING SETS` — correct **uniquement** quand aucun
filtre multi-sélection n'est actif. Dès qu'on coche une écurie, cette lecture littérale ferait
tomber les compteurs des autres écuries à zéro : elle **viole** la règle qu'elle est censée
implémenter. Neuf requêtes plutôt que 3 à 5 coûte plus de round-trips, mais chacune reste un
agrégat sur un sous-ensemble indexé de ≤ ~8000 lignes — le budget mesuré
(`docs/search-perf.md`, p95 ≈ 105 ms bout en bout) montre que la marge est large.

**Conséquences.** Si le volume dépassait largement 8000 médias, fusionner les facettes
**inactives** dans une seule requête `GROUPING SETS` (et ne garder l'agrégat dédié que pour les
facettes réellement actives, rarement plus de 2-3 à la fois) resterait l'optimisation évidente
— non faite ici faute de nécessité mesurée, à trancher sur un nouveau chiffre, pas par
anticipation.

**Le prix du « PostgreSQL pur », chiffré (ajout du 2026-08-21).** Un `GET /search` complet vaut
**21 allers-retours SQL** (résultats, `COUNT(*)`, les 9 agrégats de facette, les histogrammes).
C'est acceptable **parce que la mesure a été faite** : p95 ≈ 53 ms bout en bout sur le jeu de
démo complet, budget 300 ms — mais sur Postgres conteneurisé **en local**. Sur Neon depuis
Vercel, à 8-15 ms de RTT, ces 21 allers-retours ajoutent 170 à 315 ms de latence réseau pure,
c'est-à-dire le budget entier. **À re-mesurer au premier déploiement**, avant toute autre
optimisation : c'est le nombre de round-trips, pas le coût de chaque requête, qui vieillira mal.
Le refus d'un moteur externe (Elasticsearch, Meilisearch — hors périmètre du brief) reste le bon
choix à cette volumétrie ; il se paie ici, et nulle part ailleurs.

## Générateur de démo : `Model.__table__` (Core), jamais `Model` (ORM), pour les écritures en lot
*Décidé le 2026-08-21 — run `J2 intelligence et recherche`*

**Décision.** Toutes les écritures en lot du générateur de démo (`apex/demo/seed.py`) —
`media`, `media_series`, `media_engagement`, `media_ocr_candidate`, et les `UPDATE` en
`executemany` (`bindparam`) qui posent `series_id`/le représentant de chaque rafale — passent
par `insert(Model.__table__)`/`update(Model.__table__)` (Core pur), jamais par
`insert(Model)`/`update(Model)` (la classe ORM).

**Pourquoi.** Mesuré, pas supposé : sur ce générateur, `insert(MediaEngagement)` (ORM) exécuté
via `session.execute()` alors que l'identity map de la session porte déjà des milliers d'objets
`Media`/`MediaSeries` coûtait **~45× plus lent** que `insert(MediaEngagement.__table__)` — 4,6 s
contre 0,07 s par lot de 500 lignes (`cProfile`, dominé par l'attente réseau). Le seed complet
(~8000 médias) est passé de 89 s à ~7 s après ce seul changement, plus l'abandon de `putpixel`
pixel-à-pixel pour le dégradé des vignettes simulées (numpy vectorisé). Objectif du plan
« < 15 s » largement tenu, marge de sécurité pour un environnement de test plus lent.

**Conséquences.** Tout futur générateur/import en lot sur ce projet doit utiliser
`Model.__table__` dès qu'un volume significatif est en jeu et que la session porte déjà
beaucoup d'objets — la bascule ORM → Core doit être un réflexe de performance documenté, pas
une découverte à chaque fois. `update(Model.__table__)` en `executemany` exige
`.where(Colonne == bindparam("nom"))` avec un nom de paramètre **différent** du nom de la
colonne ciblée si on veut passer par un mode ORM ; en Core pur, le bind name est libre.

## Frontière DOE de l'OCR : le modèle produit un texte et un nombre, jamais un rattachement
*Décidé le 2026-08-21 — run `J2 intelligence et recherche`*

**Décision.** `pipeline/ocr/engine.py` est le **seul** module qui appelle le modèle, et son
unique question est « quels textes vois-tu, avec quelle confiance ». Il ne connaît ni les
engagements, ni les pilotes, ni les clients. Tout ce qui *décide* est du code exact ailleurs :
filtrage géométrique et score composite (`scoring.py`), normalisation (`normalize.py`),
**jointure SQL sur `engagement`**, application des seuils et écriture de `media_engagement` /
`attachment_status` (`classify.py`). Les Directives (`ocr_high`, `ocr_low`, ratios géométriques,
`engine_version`) vivent en table `app_setting`, éditables sans redéploiement, jamais en dur.

**Pourquoi.** C'est le seul point « IA » du projet et l'argument central de l'étude de cas
(« le déterministe reste au code »). Une frontière déclarée dans un document ne vaut rien : il
fallait la rendre **opposable**. Trois vérifications, de nature différente à dessein : un moteur
factice de dix lignes fait tourner toute la chaîne (persistance, jointure, seuils, rattachement)
— donc rien du métier ne dépend du vrai modèle ; un moteur qui **lève une exception dès qu'on le
lit** est injecté pendant toute une re-projection — donc ce chemin ne touche jamais le modèle ;
et une **analyse de l'AST** vérifie qu'aucun module de la fermeture d'imports du chemin de
re-projection n'importe `engine.py` — un test de comportement ne couvre que ce qu'il exécute,
celui-ci ferme la porte.

**Conséquences.** Remplacer le moteur (si la calibration sur photos réelles déçoit) est un
changement d'un fichier derrière le protocole `OcrEngine`. Corollaire pour la revue : le test
d'AST a d'abord été écrit sur une **liste de quatre fichiers rédigée à la main** et une
recherche de sous-chaîne — il promettait plus qu'il ne garantissait (revue J2, 🟠 6). Il a été
réécrit autour d'une vraie fermeture transitive des imports `apex.*` résolus sur le système de
fichiers, avec un plancher de taille (`>= 8` alors que la fermeture réelle vaut 12) posé
volontairement **sous** la valeur mesurée pour ne pas recréer une liste figée déguisée. Toute
extension du chemin de re-projection reste donc couverte sans maintenance.

## Candidats OCR bruts persistés : changer un seuil re-projette, sans jamais ré-inférer
*Décidé le 2026-08-21 — run `J2 intelligence et recherche`*

**Décision.** `media_ocr_candidate` persiste la sortie brute du modèle — texte lu, score, boîte,
`engine_version`. `PUT /settings/ocr` écrit les Directives puis enqueue `reclassify_ocr`, qui
**re-projette les candidats existants** dans auto / validation / abstention. Aucun chemin de
reclassement ne relit une image. Quatre issues, dont une hors bande de seuils : `not_engaged`
(numéro absent de la table des engagements) est un signal **métier**, jamais un échec du
modèle — baisser un seuil ne fait pas apparaître une voiture qui n'est pas au départ, et rien
n'est jamais rattaché de force.

**Pourquoi.** Le critère d'acceptation « changer les seuils redistribue les cas » n'est
démontrable en direct que si la redistribution est instantanée. Ré-inférer coûterait ~41 min
pour 8 000 médias (311 ms/image mesurés, aperçu 1600 px, CPU) ; re-projeter tient en quelques
secondes, par tranches de 500. C'est ce qui transforme le curseur de seuils en argument de
démonstration plutôt qu'en réglage de fichier de configuration.

**Conséquences.** Les décisions humaines (`accepted`/`rejected`) et les rattachements manuels
(`source='human'`) sont **terminaux** : ils survivent à tout changement de seuil, à toute
re-projection, à tout rejeu de `ocr_media`. Corollaire découvert en revue : tout chemin qui
défait un rattachement d'origine machine doit d'abord rendre la décision humaine terminale
(candidats visés passés en `rejected`, `engagement_id = None`) **avant** la re-projection —
sinon celle-ci recalcule `auto` et réinsère le lien avant le commit, et l'API répond `204` en
n'ayant rien supprimé. Enfin, deux Directives (`min/max_box_area_ratio`) n'agissent qu'à
l'inférence : les modifier ne redistribue rien et fait cohabiter deux millésimes de score dans
le catalogue — dette assumée, à traiter si elles deviennent réellement éditables.

## Calibration des seuils : ce que l'évaluation offline a corrigé du plan
*Décidé le 2026-08-21 — run `J2 intelligence et recherche`*

**Décision.** Les seuils par défaut sont `high = 0,85` / `low = 0,45`, mesurés et non choisis :
`pytest -m ocr_eval` (hors suite par défaut) balaie les seuils sur un jeu synthétique à vérité
terrain et retient le premier point tenant une **précision ≥ 98 % dans la bande auto**. Le
livrable n'est pas un chiffre mais un **protocole** : rejouer l'évaluation sur le jeu réel une
fois sourcé (`OCR_EVAL_DATASET=…`), lire les deux nombres, les saisir dans l'UI. Aucune ligne de
code à modifier.

**Pourquoi.** Trois constats de la mesure ont changé le code ou la méthode, et aucun n'était
prévisible sur le papier :

1. **Le seuil du plan (0,80) ne tenait pas la cible** — 97,7 % de précision, 5 rattachements
   erronés. Le gate a échoué comme il devait. Passer à 0,85 coûte 2,5 points d'automatisme
   (59,4 % → 56,9 %) et retire un faux positif sur cinq : une abstention coûte un clic, un faux
   positif livre une photo au mauvais client.
2. **Un facteur `f_pureté` a été ajouté à la formule du plan** (`conf × f_géométrie ×
   f_longueur`). La regex `^[0-9]{1,3}$` ne protège de rien une fois les confusions
   typographiques appliquées : « MICHELIN » devient « 111 », « SO » devient « 50 », avec la
   confiance du modèle intacte — un flanc de pneu rattachait des photos au n°111. `f_pureté` est
   la proportion de caractères déjà chiffres **avant** substitution, planchée à 0,30 : coût nul
   sur une lecture propre, effondrement du score sur une lecture reconstruite.
3. **La densité du plateau est le paramètre le plus sensible de toute la mesure.** Une première
   version du jeu tirait les numéros au hasard et simulait un plateau de 168 voitures : 92,2 %
   de précision. Avec une table des engagements réaliste (44 voitures, `ENTRY_LIST_SIZE`), la
   même chaîne mesure 98,0 %. Corriger la simulation n'était pas une complaisance, c'était la
   condition pour que le chiffre veuille dire quelque chose.

**Conséquences.** Règle de publication : **le taux de rattachement automatique ne se cite jamais
sans la taille du plateau** — le rapport généré (`docs/ocr-eval.md`, artefact, jamais édité à la
main) le met en tête. Le seuil recommandé est un ordre de grandeur, pas une valeur à trois
décimales : sur 205 rattachements, une erreur pèse 0,49 point et l'intervalle de confiance à
95 % vaut ±1,9 point — la colonne de précision du balayage n'est d'ailleurs pas monotone. Enfin,
la classe d'erreur résiduelle est **irréductible** et mérite de figurer dans l'étude de cas :
les 4 erreurs restantes sont toutes un chiffre occulté (`313` lu `13`) dont la troncature tombe
par malchance sur un autre numéro engagé — un humain lit la même chose, et le seul garde-fou
disponible (la table des engagements) ne joue pas dans ce cas. C'est l'argument même de
l'arbitrage humain.

## Indicateurs de rattachement automatique : deux grains, un invariant, une ventilation
*Décidé le 2026-08-21 — run `J2 intelligence et recherche`*

**Décision.** Deux indicateurs coexistent et ne comptent **pas** la même chose, par
construction : `GET /settings/ocr → distribution.auto` compte des **candidats**
(`media_ocr_candidate` en résolution `auto`/`accepted`) ; `GET /stats/auto-attach-rate →
auto_ocr` compte des **médias** portant au moins un `media_engagement` qu'aucun humain n'a
touché. La différence est documentée dans la docstring de `routers/stats.py`. Ce qui est absolu,
en revanche, c'est l'invariant : **une baisse du seuil haut ne fait jamais reculer aucun des
deux.** Un test de propriété cross-endpoints le verrouille (snapshot avant/après un
`PUT /settings/ocr` sur seed réel). Par ailleurs, `auto-attach-rate` **ventile** son calcul en
`real` / `simulated`, et `GET /search` expose un filtre `is_simulated` à trois états.

**Pourquoi.** L'invariant a été formulé parce qu'il a été enfreint : en démonstration, baisser
le seuil faisait **reculer** `auto_ocr` de 178 pendant que `distribution.auto` et la facette
`engagement_attached` avançaient de 236 — deux écrans qui se contredisent devant le prospect,
sur le point précis que le brief met en avant. Cause réelle (l'hypothèse « écrasement par un
autre chemin » était fausse) : le générateur de démo posait un `media_engagement` pour les
médias `pending_review`, un état **impossible en production** puisque la file de validation est
précisément l'ensemble des candidats non encore matérialisés. `auto_ocr` était donc gonflé de la
taille de la file (414) au sortir d'un seed frais, et la première re-projection nettoyait ces
liens fantômes. La ventilation `real`/`simulated`, elle, répond à une exigence de probité : on
ne fait pas passer un jeu généré pour du traitement réel — un dirigeant qui lit `real.total = 0`
ne prend pas 7 842 médias simulés pour un taux acquis.

**Conséquences.** Deux métriques de grains différents sur le même phénomène exigent un **test
d'accord**, pas deux tests séparés — chacune peut être juste isolément pendant que le couple
ment. Le correctif porte sur l'**écriture** (le générateur ne produit plus la donnée
impossible), jamais sur la lecture : filtrer `auto_ocr` aurait masqué le symptôme et rendu
l'indicateur incohérent avec son propre contrat. Toute nouvelle métrique exposée au tableau de
bord doit déclarer son grain et, si elle recoupe une autre, être couplée à elle par un invariant
testé.

## Visibilité par défaut d'une liste de médias : une source unique, paramétrée par colonnes
*Décidé le 2026-08-21 — run `J2 intelligence et recherche`*

**Décision.** Les trois règles qui déterminent « ce qu'une liste de médias montre par défaut »
vivent dans `services/access.py` et nulle part ailleurs : `series_collapse_clause` (repli des
rafales, **avec** sa clause de défense « média sans shooting »), `exclude_duplicates_clause`
(doublons exclus) et `media_visibility_clause_for` (cloisonnement par rôle). Elles sont
paramétrées **par colonnes** (`InstrumentedAttribute`), pas par modèle : `Media` et
`MediaSearch` portent les mêmes noms de colonnes sans être la même classe SQLAlchemy. `/media`
et `/search` les consomment ; un test d'accord compare les deux routes sur leur population
commune.

**Pourquoi.** Le motif s'est rejoué **trois fois**. (1) En clôture de J1, le repli des rafales
masquait les orphelins de `GET /media` — corrigé par une clause `or_` inline. (2) En J2,
`services/facets.py` avait réimplémenté la même règle sans reprendre cette clause : `/search`
masquait l'**intégralité** du bac « à rattacher » (374 médias, `total = 0`), puisqu'un média
sans shooting ne passe jamais par le regroupement de rafales et reste donc
`is_series_representative = False`. (3) La revue J2 a trouvé la même duplication sur le
cloisonnement de rôle, avec un enjeu plus fort encore. Deux implémentations d'une même règle
divergent toujours ; le passage par colonnes explicites force chaque appelant à fournir ses
arguments, et c'est **cette explicité** qui rend l'oubli visible à l'écriture — pas un mécanisme
de type.

**Conséquences.** Toute nouvelle route qui liste des médias passe par ces trois prédicats, sans
exception. La forme de test qui a fermé le sujet est un **test d'accord entre consommateurs**
(`tests/search/test_media_search_agreement.py`), pas un test par route : deux routes peuvent
être vertes séparément tout en se contredisant. Attention à ne pas mal lire les chiffres : sur
le jeu de démo, `/search?status=inconsistent` renvoie 22 et non 95 — les 73 manquants sont des
membres non représentatifs d'une **vraie** rafale, légitimement repliés, comme `/media` les
replie déjà.

## Version Python figée à 3.12 et validation d'installation de production
*Décidé le 2026-08-21 — run `préparation déploiement`*

**Décision.** `pyproject.toml` fixe `requires-python = ">=3.12,<3.13"` — jamais 3.13, malgré
Vercel qui supporte les deux (3.12 par défaut, 3.13 et 3.14 disponibles). `bash
scripts/check_prod_install.sh` (conteneur Linux jetable, `pip` réel, mode empreintes) devient
un passage obligé avant tout déploiement : il installe `requirements.txt` exactement comme le
ferait le builder Vercel, substitue `opencv-python-headless` à `opencv-python`, vérifie que
l'application importe, et mesure le poids décompressé contre le plafond de 250 Mo.

**Pourquoi.** Deux jalons complets (J1, J2), plusieurs revues et une passe d'intégration se
sont succédé sans que rien ne révèle que **le projet ne s'installe pas en production** —
personne n'avait jamais tenté une installation de production. `requires-python = ">=3.13"`
était présent dès le premier commit (`feat(socle)`), alors que le plan avait décidé Python 3.12
(§3-B) ; `rapidocr-onnxruntime` (moteur OCR, Décision J), choisi *précisément* parce qu'il tient
dans le budget Vercel, n'a **publié aucune version compatible Python 3.13** sur PyPI, de la
première à la dernière (1.4.4, vérifié par requête directe à l'API PyPI). `uv sync` en local
installe pourtant `rapidocr-onnxruntime==1.4.4` sur Python 3.13.5 sans se plaindre — `uv` ne
rejette pas cette combinaison aussi strictement que `pip`, qui refuse purement et simplement de
résoudre le paquet (`Could not find a version that satisfies the requirement`). Le poste de
dev « fonctionnait » ; seule une tentative d'installation par `pip`, dans un environnement
Linux réel, révèle le problème — c'est exactement ce que fait le builder Vercel, et exactement
ce que rien ne testait jusqu'ici.

Deux artefacts supplémentaires de `requirements.txt` (généré par `uv export --no-dev
--format requirements-txt`) auraient de toute façon fait échouer l'installation même sur
Python 3.12 : une ligne `-e .` sans hachage, qui casse le mode empreintes de `pip` dès qu'une
autre ligne porte un hachage (systématique dès que `uv export` inclut le paquet local) — corrigé
par `--no-emit-project` et une installation séparée (`pip install --no-deps -e .`) ; et une
première ligne parasite (`Resolved N packages…`, un message de statut `uv` capturé par erreur)
qui rend le fichier invalide pour `pip` dès la première ligne.

**Conséquences.** `uv sync`/`uv run` valident un environnement de **développement**, jamais une
installation de **production** — les deux ont divergé une fois déjà et rien n'empêche que cela
se reproduise sur un autre paquet. `check_prod_install.sh` est le garde-fou : toute dérive
future (borne `requires-python` remontée sans vérification, nouvelle dépendance sans wheel pour
la version cible, `requirements.txt` mal régénéré) échoue à l'exécution du script, avant un
déploiement, plutôt qu'au premier déploiement réel. `api/index.py` ajoute par ailleurs `src/` à
`sys.path` en défense en profondeur : l'import de `apex` ne dépend plus uniquement de la
réussite de l'installation éditable séparée (`pip install --no-deps -e .`), dont on ne peut pas
vérifier depuis ici si le builder Vercel l'exécute réellement telle quelle.

## Poids d'une fonction Vercel Python : 250 Mo, mesurés, pas supposés
*Décidé le 2026-08-21 — run `préparation déploiement`*

**Décision.** `opencv-python` (tiré transitivement par `rapidocr-onnxruntime`) est remplacé par
`opencv-python-headless`, **même version exacte**, appliqué par `check_prod_install.sh`
(`pip uninstall` puis `pip install --no-deps`, jamais une simple installation par-dessus, pour
ne laisser aucun fichier orphelin de la variante GUI). L'évaluation offline
(`pytest -m ocr_eval`) a été rejouée après substitution : **56,9 % d'automatique, 98,0 % de
précision, chiffres strictement identiques** — aucun changement de comportement du moteur.
`python-jose[cryptography]` → `python-jose` et `uvicorn[standard]` → `uvicorn` sont préparés
(le JWT du projet est HS256 exclusivement, qui ne requiert aucun backend asymétrique ; le
serveur ASGI n'est jamais importé par le code applicatif, seulement invoqué en local — Vercel
invoque directement l'objet `app`), mais **pas encore appliqués** au dépôt réel : ces deux
changements modifient `pyproject.toml`/`uv.lock`, ce qu'on ne peut pas faire sans resynchroniser
le `.venv` partagé (voir `docs/wiki/pieges-projet.md`).

**Pourquoi.** Mesuré (`services/api/requirements.txt` réel, installé par `pip` dans
`python:3.12-slim`, Linux) : **581 Mo** décompressés avec `opencv-python`, **546 Mo** après
substitution headless — un gain réel mais modeste (35 Mo ; l'essentiel du poids d'OpenCV n'est
pas dans les bibliothèques GUI mais dans le module `cv2` compilé lui-même, partagé par les deux
variantes). Sans le moteur OCR du tout, l'API tombe à **292 Mo**, et à **251 Mo** (238 Mo hors
`pip`, un outil de build qui ne fait probablement pas partie du paquet livré) une fois les deux
substitutions `jose`/`uvicorn` ajoutées — **sous le plafond**, marge d'environ 12 Mo. Mais le
worker qui draine la file de jobs (`apex/queue/runner.py::drain`) traite **tous** les types de
jobs par le même code générique — `ingest_media`, `finalize_batch`, `ocr_media`,
`build_delivery`, `demo_reset` — donc a besoin de `botocore` (dépôt S3), `faker` (jeu de démo)
**et** du moteur OCR simultanément : sa version « tout compris », même avec toutes les
substitutions sûres, pèse **509 Mo**, très au-delà du plafond, quelles que soient les
réductions de dépendances raisonnables tentées (`onnxruntime` 66 Mo + `cv2`/`opencv-python-
headless.libs` 153 Mo + `numpy`/`numpy.libs` 71 Mo à eux seuls dépassent le budget entier).
**Réduire les dépendances ne suffit pas** : le moteur OCR, à lui seul, coûte plus que le budget
complet d'une fonction.

**Conséquences.** Le risque R4 du plan (§ tableau des risques, « Repli : OCR exécuté uniquement
par le worker local, l'OCR en ligne étant alors servi par les données seedées ») n'est plus une
hypothèse — la mesure le rend nécessaire, pas seulement possible, **si l'API principale et le
drainage de la file restent une seule fonction Vercel**. Deux directions restent ouvertes, ni
l'une ni l'autre implémentée à ce stade — décision à prendre explicitement, jamais en silence
(même principe que R1) :
1. **Isoler `ocr_media` dans un déploiement dédié** — **mesurée, écartée par les chiffres**, pas
   par supposition. Jeu de dépendances minimal d'une fonction dédiée (inférence + lecture/
   écriture en base + lecture du fichier sur le stockage objet, sans `faker`, sans
   FastAPI/`uvicorn`, sans `alembic`, sans `jose`/`bcrypt`, sans `typer`/`rich` — composé à
   partir des imports réels de `apex/queue/handlers/ocr_media.py` et de sa fermeture) : **437 Mo
   hors `pip`**, mesuré dans les mêmes conditions (conteneur Linux, Python 3.12, `pip` réel,
   `opencv-python-headless`). Dépassement de **187 Mo (+75 %)**, porté quasi entièrement par le
   moteur d'inférence lui-même (`onnxruntime` 66 Mo + `cv2`/`opencv-python-headless.libs` 153 Mo
   + `numpy`/`numpy.libs` 71 Mo + `shapely`/`pyclipper` 16 Mo ≈ 322 Mo à eux seuls, avant même la
   base de données ou le stockage objet). Aucune réduction raisonnable ne comble cet écart : ce
   n'est pas une question de dépendances annexes, c'est le moteur qui ne tient pas, seul, dans
   une fonction Vercel. **Option écartée.**
2. **OCR uniquement par le worker local/CLI** (`apex.cli worker --loop`), jamais par
   `POST /jobs/tick` en ligne — la démonstration en ligne s'appuie sur le jeu déjà seedé
   (rattachements OCR déjà calculés, visibles, cliquables). Coût démo : une nouvelle photo
   uploadée **via le site en ligne** n'obtient pas de rattachement automatique immédiat (elle
   part en validation manuelle comme n'importe quel cas `review`/`abstain` — rien ne casse,
   mais rien ne « wow » en direct sur un upload fait pendant l'appel). Coût d'ingénierie :
   faible, aligné sur le repli déjà anticipé par le plan (R4). **Seule option qui reste viable
   dans la stack actuelle** — retenue par élimination mesurée, pas par défaut.
   **Implémentée le 2026-08-21**, voir la décision suivante.

**Mesure finale après implémentation** (`bash scripts/check_prod_install.sh`, conteneur
Linux, `pip` réel) : **214,8 Mo hors `pip`**, soit ~35 Mo de marge sous le plafond — meilleur
que les 238 Mo estimés plus haut, l'estimation partant d'un jeu de dépendances reconstitué à
la main quand la mesure part du `requirements.txt` réellement exporté. Le poids restant est
dominé par `numpy` (43 Mo + 28 Mo de `numpy.libs`, requis par le hash perceptuel), `botocore`
(30 Mo) et `faker` (25 Mo, jeu de démo) — trois pistes de réduction si la marge devait un jour
se resserrer, aucune nécessaire aujourd'hui.

## Bascule vers Supabase : aligner le portfolio plutôt qu'optimiser chaque projet
*Décidé le 2026-08-21 — run `bascule Supabase`*

**Décision.** Base managée **et** stockage objet chez Supabase (région UE), à la place de
Neon + Cloudflare R2. Deux chaînes de connexion : `DATABASE_URL` (Transaction pooler, port
6543) pour l'API, `DATABASE_URL_DIRECT` (Session pooler, 5432) pour Alembic.

**Pourquoi.** Cardan, la première application du portfolio, tourne déjà là-dessus. Aligner
les deux projets vaut plus qu'un arbitrage optimal projet par projet : un seul fournisseur à
administrer, une seule facture à surveiller, **un seul jeu de pièges déjà payés** — et ils
sont réels (voir ci-dessous). Le gain technique accessoire est qu'un projet Supabase fournit
la base *et* le stockage : une ressource externe à créer au lieu de deux.

L'argument qui avait écarté Supabase — mise en pause après sept jours d'inactivité — n'a pas
disparu, il est accepté : la démonstration se réveille avant un rendez-vous, comme celle de
Cardan. Il interdit en revanche une idée qui paraissait raisonnable : **un cron
hebdomadaire serait le pire des rythmes**, puisqu'il tombe exactement sur le seuil de pause.

**Trois pièges hérités de Cardan, pris en compte sans avoir eu à les rencontrer.**
1. L'onglet « Direct connection » (`db.<ref>.supabase.co`) ne publie **qu'un enregistrement
   AAAA (IPv6)** : inutilisable depuis tout réseau sans IPv6. C'est pourtant celui que la
   documentation Supabase met en avant.
2. Un pooler en mode transaction ne peut pas porter une migration de schéma — d'où la
   seconde URL, réservée à Alembic.
3. Les instructions préparées ne survivent pas au multiplexage : `prepare_threshold=None`
   dès que `APP_ENV != local`. Sans cela, psycopg réutilise une instruction posée sur une
   autre session backend et la requête échoue, de façon intermittente et incompréhensible.

**Conséquences.** `pool_recycle=280` s : Supavisor ferme les connexions inactives autour de
cinq minutes, et tirer une connexion morte du pool coûte un aller-retour perdu au réveil.
Le backend S3 (`boto3`) parle à l'endpoint S3-compatible de Supabase sans code spécifique —
**non vérifié faute de compte**, premier point à contrôler après le déploiement, avec R2 en
repli sans changement de code. Enfin `S3_REGION` est la région réelle du projet, jamais
`auto` comme chez R2.

## Espace client : cloisonné par construction, des deux côtés
*Décidé le 2026-08-21 — run `J3 livraison et facturation`*

**Décision.** Le lien de partage est un jeton opaque de 256 bits dont la base ne stocke que
le `sha256`. Il s'échange contre un JWT de session de 30 minutes (`scope='client'`), et
c'est ce jeton court qui accompagne chaque requête, y compris chaque image. Le routeur
`/public` n'a **qu'une** dépendance d'authentification, n'accepte **aucun** identifiant de
collection ou de client en paramètre, et répond `404` — jamais `403` — hors périmètre.

**Le cloisonnement vaut aussi côté navigateur.** `lib/client/session.ts` ne partage rien
avec `lib/auth/session.ts` : clé de stockage distincte, jeton passé explicitement à chaque
appel, jamais `getToken()`. Le cloisonnement serveur n'aurait aucun intérêt si le frontend
pouvait emprunter une session studio restée ouverte dans le même navigateur — et la faute
serait invisible en revue, puisque tout continuerait de fonctionner.

**Pourquoi un jeton opaque plutôt qu'un JWT dans l'URL.** Un JWT n'est pas révocable, or la
révocation est un critère du brief. Et **la révocation est vraiment immédiate** :
`security.get_client_scope` relit le lien en base à *chaque* requête, pas seulement à
l'ouverture de session. Sans cette relecture, un lien révoqué resterait exploitable jusqu'à
l'expiration du JWT, soit une demi-heure. Un `SELECT` sur clé primaire est le prix
négligeable de cette garantie.

**Conséquences.** Personne ne peut réafficher un lien, pas même le studio : l'écran de
partage insiste donc sur la copie unique, et la liste des liens ne montre que des
silhouettes. Le test d'isolation est **paramétré sur les routes découvertes dans
l'OpenAPI** — toute route `/public` ajoutée plus tard est couverte sans que personne y
pense. Enfin, un `410` reçu en cours de session mène à la page « Ce lien n'est plus
valide », qui n'affiche aucune trace technique : c'est un critère d'acceptation, pas une
politesse.

## Filigrane : cuit à l'ingestion pour l'aperçu, appliqué au vol pour la vignette
*Décidé le 2026-08-21 — run `J3 livraison et facturation`*

**Décision.** L'aperçu porte son filigrane dans ses pixels, écrit une fois à l'ingestion.
La vignette **stockée** reste propre et c'est la copie **servie au client** qui est
filigranée, à la volée (`derivatives.watermark_encoded_image`).

**Pourquoi cette asymétrie.** Le pHash et la netteté sont calculés sur la vignette : un
filigrane cuit dedans introduirait une texture répétée qui fausserait la DCT basses
fréquences et la variance de Laplacien — deux doublons légitimement identiques pourraient
diverger, et le choix du représentant le plus net serait biaisé par la densité du filigrane
plutôt que par le contenu. L'écart avait été signalé en revue J1 et laissé ouvert avec sa
piste de résolution ; c'est exactement celle qui est appliquée ici.

**Conséquences.** Un décodage/ré-encodage par vignette servie, compensé par un `ETag` et un
`Cache-Control: private` — le navigateur du client ne la redemande pas. L'`ETag` porte la
variante : sans ce suffixe, vignette et aperçu du même média partageaient une empreinte et
le navigateur servait l'une pour l'autre (constaté). Et la police par défaut de Pillow ne
couvrant que l'ASCII, le texte du filigrane est translittéré : « Studio Chicane — aperçu »
s'y dessinait « Studio Chicane ▯ aper▯u ».

## Le jeu de démonstration doit être livrable, pas seulement affichable
*Décidé le 2026-08-21 — run `J3 livraison et facturation`*

**Décision.** Les trois variantes d'un média simulé pointent le même fichier du pool. Le
générateur posait auparavant `storage_key_hd = None`, par une décision d'origine
raisonnable (§3-N.1 : quarante vignettes partagées, jamais de fichier grand format, pour ne
pas gonfler un environnement jetable).

**Pourquoi.** En J3, `build_delivery` refuse — à raison — de construire une archive
incomplète : livrer sans le dire serait le rejet silencieux que ce projet s'interdit.
Conséquence non anticipée : **aucune collection du jeu de démonstration n'était livrable**,
et la fonctionnalité la plus démonstrative du jalon restait invisible pendant une
démonstration.

**Comment ça a été trouvé, et pourquoi ça compte.** En jouant le parcours complet contre
l'API réelle (`scripts/verify_j3_flow.py`), jamais en test : chaque test fabrique ses
propres médias, avec un fichier haute définition. C'est le troisième écart de ce projet que
seule la confrontation aux données réelles révèle, après `requires-python = ">=3.13"` et
l'installation de production. Le motif est constant — **un environnement de test bien isolé
teste ce qu'il fabrique, pas ce qui existe.**

**Conséquences.** Le fichier livré en démonstration est une vignette, pas un cliché pleine
résolution — même compromis que partout dans ce générateur : des données crédibles dans
leur forme, jamais dans leur poids. `scripts/verify_j3_flow.py` est versionné et joue 34
vérifications de bout en bout ; il n'a pas sa place dans `pytest` (il touche la base de
développement et dépend d'un serveur), et c'est précisément ce qui fait sa valeur.

## Séparation des pilotes par capacité d'exécution, détectée et non configurée
*Décidé le 2026-08-21 — run `préparation déploiement`*

**Décision.** Chaque handler déclare ce qu'il exige (`@handler("ocr_media", requires=(OCR_ENGINE,))`),
chaque processus détecte ce qu'il a (`queue/capabilities.py`, par `importlib.util.find_spec`),
et `drain()` exclut de la **réclamation** les types de jobs que ce processus ne peut pas
exécuter (`registry.unservable_kinds` → `claim.claim_batch(excluded_kinds=...)`). Ces jobs
restent `pending`, intacts, comptés dans un nouveau champ `deferred` exposé au contrat
(`TickResponse`, `QueueStats`). Le pilote CLI, lui, ne configure rien : sur un poste où l'extra
`ocr` est installé, il réclame tout.

**Pourquoi.** L'alternative — laisser la fonction Vercel réclamer un `ocr_media` qu'elle ne peut
pas exécuter — produit trois échecs puis un job `dead` : le média perd son rattachement
automatique et atterrit en validation manuelle, sans que rien n'indique que la cause est un
paquet absent plutôt qu'une photo illisible. L'invariant « le pipeline ne perd jamais un
fichier, jamais de rejet silencieux » s'applique à la file autant qu'à l'ingestion.

**Détecté, jamais configuré**, et c'est le cœur de la décision : une variable d'environnement
(`WORKER_SKIP_KINDS=ocr_media`) aurait marché tant que personne ne l'oublie au déploiement — or
ce projet a **déjà** payé le prix d'un garde-fou neutralisé par un défaut mal choisi (§
« Authentification, cloisonnement et garde-fou de secrets », où un premier correctif avait fait
de `local` le défaut d'`APP_ENV`, rendant le contrôle inopérant précisément dans le cas visé).
Ici, l'installation *est* la configuration : un environnement sans le moteur ne peut pas se
tromper sur ce qu'il sait faire.

**Une exclusion, jamais une liste blanche.** Le filtre porte sur les `kind` *enregistrés et non
servables*, pas sur les `kind` servables. Un `kind` inconnu du registre reste réclamable et
échoue explicitement (§3-E.3) ; une liste blanche l'aurait rendu invisible et l'aurait laissé
dormir en file — le silence exact que la règle interdit. Un test le verrouille
(`tests/queue/test_capability_filtering.py`), de même que le fait qu'un job différé **en tête de
file** ne consomme pas le lot (`LIMIT` s'applique après le filtre, sinon un `ocr_media`
prioritaire gèlerait toute la file en ligne).

**Conséquences.** `reclassify_ocr` reste exécutable en ligne — re-projeter des seuils rejoue des
candidats déjà stockés sans jamais ré-inférer (§ « Calibration des seuils ») : changer un seuil
depuis la démo en ligne fonctionne, seule la première lecture d'une photo neuve attend un worker.
Ajouter un jour un job qui exige une dépendance lourde ne demande qu'une entrée dans
`_CAPABILITY_MODULES` et un `requires=` sur son handler. Enfin, le worker CLI **avertit** au
démarrage si une capacité manque (`⚠ moteur OCR absent…`) : côté serverless l'exclusion est
voulue, sur un poste c'est presque toujours une erreur d'installation.
