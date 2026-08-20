---
type: architecture
maj: 2026-08-20
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

**Décision.** Neon (Francfort) pour la base managée. **Une seule révision Alembic par jalon**
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
