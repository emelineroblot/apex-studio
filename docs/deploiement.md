# Déploiement — Apex

Environnement de démonstration **jetable** : recréable de bout en bout depuis ce dépôt et le
générateur de jeu de démo. Aucune donnée à préserver, aucune dette de migration à ménager.

Même hébergement que **Cardan**, la première application du portfolio : deux projets Vercel
et un projet Supabase (base *et* stockage), offres gratuites, région UE. Les pièges
rencontrés là-bas sont déjà pris en compte ici — ils sont signalés au fil du texte.

> Ce document est opératoire (le *comment*). Les décisions et leurs raisons sont dans
> `docs/wiki/architecture.md`.

## En ligne

| | |
|---|---|
| **Démonstration** | https://apex-web-emdigital.vercel.app |
| **API** | https://apex-api-emdigital.vercel.app |
| Base et stockage | Supabase `hvpfqzegwfnvrccjnhkf`, région `eu-central-1` (Francfort) |
| Fonctions | Vercel région `fra1`, à côté de la base |

Déployé le 2026-08-22. Parcours complet rejoué contre cette instance :
`python scripts/verify_j3_flow.py https://apex-api-emdigital.vercel.app`, **34
vérifications sur 34**. Les identifiants de démonstration sont publiés par
`GET /api/v1/demo/accounts` — c'est voulu, l'écran de connexion s'en sert.

## Ce qui est déployé, et ce qui ne l'est pas

| Où | Quoi |
|---|---|
| Projet Vercel `apex-web` (root `apps/web`) | Next.js — l'interface |
| Projet Vercel `apex-api` (root `services/api`) | L'API Python et **tout le pipeline sauf l'OCR** |
| Projet Supabase | PostgreSQL + Storage |
| Poste de développement, à la demande | `apex.cli worker --loop` — la lecture des numéros de course |

Deux projets Vercel parce qu'un projet n'a qu'un runtime de build (plan, §3-A). Le frontend
appelle l'API par `NEXT_PUBLIC_API_BASE_URL` ; l'API n'autorise en CORS que `WEB_ORIGIN`.

**L'OCR ne tourne pas en ligne, et c'est une décision mesurée** : le moteur pèse ~322 Mo à
lui seul, pour un plafond de 250 Mo par fonction. En ligne, un lot déposé est ingéré, daté,
rattaché à son shooting, dédoublonné et regroupé en séries — en direct. Seule la lecture du
numéro attend un worker. Le jeu de démo étant seedé avec ses rattachements OCR déjà
calculés, la démonstration est complète sans worker ; il ne sert qu'aux photos ajoutées
après coup.

## 1. Le projet Supabase

Créer un projet en région UE (`eu-west-1` ou `eu-central-1`), puis relever **deux** chaînes
de connexion dans *Project Settings → Database → Connection string* :

| Variable | Onglet | Port | Usage |
|---|---|---|---|
| `DATABASE_URL` | **Transaction pooler** | 6543 | Toutes les requêtes de l'API |
| `DATABASE_URL_DIRECT` | **Session pooler** | 5432 | Alembic, uniquement |

Les deux ont la forme :

```
postgresql+psycopg://postgres.<ref>:<mot-de-passe>@aws-0-<region>.pooler.supabase.com:<port>/postgres
```

⚠️ **Ne pas prendre l'onglet « Direct connection »** (`db.<ref>.supabase.co`), pourtant mis
en avant par la documentation Supabase : il ne publie qu'un enregistrement AAAA (IPv6) et
échoue avec `failed to resolve host` depuis tout réseau sans IPv6. Constaté sur Cardan, même
plateforme.

**Pourquoi deux URL.** Le pooler en mode transaction multiplexe les connexions : il ne peut
porter ni une migration de schéma, ni rien qui exige une session à soi. Le code s'en occupe
seul — `alembic/env.py` prend `DATABASE_URL_DIRECT` quand elle existe, et `db.py` désactive
les instructions préparées (`prepare_threshold=None`) dès que `APP_ENV != local`, sans quoi
psycopg réutiliserait une instruction posée sur une autre session backend.

Créer ensuite un bucket **privé** (`apex-media`) dans *Storage*, puis une paire de clés dans
*Storage → Settings → S3 connection*. L'endpoint se termine par `/storage/v1/s3` et la
région est celle du projet — jamais `auto`, contrairement à Cloudflare R2.

> Le backend S3 d'Apex (boto3) parle à l'endpoint S3-compatible de Supabase **sans une
> ligne de code spécifique** — vérifié le 2026-08-22 sur un aller-retour complet :
> écriture, relecture comparée octet à octet, taille, existence, listing par préfixe,
> écriture en flux, suppression. Cardan était passé par l'API REST Supabase ; ce détour
> n'est pas nécessaire ici.

## 2. Les variables d'environnement

`services/api/.env.example` fait foi pour la liste complète. Sur le projet `apex-api` :

| Variable | Valeur |
|---|---|
| `APP_ENV` | `production` (ou n'importe quoi sauf `local`) |
| `DATABASE_URL` | Transaction pooler, port 6543 |
| `DATABASE_URL_DIRECT` | Session pooler, port 5432 |
| `JWT_SECRET`, `WORKER_SECRET`, `CRON_SECRET` | **trois valeurs aléatoires distinctes** |
| `DEMO_OWNER_PASSWORD`, `DEMO_PHOTOGRAPHER_PASSWORD` | à choisir — ils sont publiés par `GET /demo/accounts` |
| `STORAGE_BACKEND` | `s3` |
| `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | le bucket Supabase |
| `WEB_ORIGIN`, `PUBLIC_WEB_BASE_URL` | l'URL du projet `apex-web` |

Sur le projet `apex-web` : `NEXT_PUBLIC_API_BASE_URL` (URL de `apex-api`, **sans**
`/api/v1`) et `NEXT_PUBLIC_API_MODE=live`.

⚠️ `APP_ENV` vaut `production` par défaut **volontairement** : l'application refuse de
démarrer si un secret a encore sa valeur du dépôt. Le dépôt est public, ces valeurs sont
connues de tous. Un démarrage qui échoue avec un message clair vaut mieux qu'une démo
ouverte à quiconque lit le code.

## 3. La mise en ligne

```bash
# Garde-fou — jamais optionnel (voir docs/wiki/pieges-projet.md)
cd services/api && bash scripts/check_prod_install.sh

# Schéma et jeu de démo, poussés depuis le poste vers les ressources en ligne
export DATABASE_URL='postgresql+psycopg://postgres.<ref>:...@...:6543/postgres'
export DATABASE_URL_DIRECT='postgresql+psycopg://postgres.<ref>:...@...:5432/postgres'
export STORAGE_BACKEND=s3 S3_ENDPOINT_URL=… S3_BUCKET=… S3_ACCESS_KEY_ID=… S3_SECRET_ACCESS_KEY=…
uv run alembic upgrade head
uv run python -m apex.cli seed --reset

# Déploiement : deux projets, root dirs distincts, à lier une fois
#   apex-api : root = services/api  |  apex-web : root = apps/web
```

**Le seed se lance depuis un poste, jamais en ligne.** Il écrit dans la base *et* dans le
bucket : c'est le mode opératoire normal ici, pas un contournement. Compter plusieurs
minutes — l'essentiel du temps part dans l'envoi des images, une requête réseau par fichier.
Sur Cardan, mesuré à ~173 ms par photo depuis un poste, davantage depuis une fonction.

## 4. Faire tourner l'OCR pendant une démonstration

Depuis le poste, avant le rendez-vous, avec les mêmes variables qu'à l'étape 3 :

```bash
cd services/api
uv sync --extra ocr                          # une fois : le moteur n'est pas dans le jeu par défaut
uv run python -m apex.cli worker --loop
```

Le worker se connecte à la base et au stockage **en ligne** : il n'a rien de local sinon le
processus. Il traite les `ocr_media` que la fonction Vercel a laissés en file — visibles à
tout moment dans `deferred` (`GET /api/v1/queue/stats`). S'il démarre en affichant
`⚠ moteur OCR absent`, l'extra `ocr` n'est pas installé.

## 5. Remettre la démonstration à neuf

**Il n'y a pas de cron**, délibérément — même choix que Cardan : une exécution planifiée non
surveillée coûte des centaines d'occasions d'échec par an, pour un besoin qui ne se présente
qu'avant un rendez-vous ou après le passage d'un visiteur brouillon.

Deux façons de le faire, dans cet ordre de préférence :

1. **Depuis un poste** — `uv run python -m apex.cli seed --reset` avec les variables de
   production. Aucune limite de durée, sortie observable.
2. **Depuis l'application** — `POST /api/v1/demo/reset` (rôle dirigeant) enfile un job et
   répond `202`. ⚠️ Le travail réel dépassera très probablement les 300 s d'une fonction
   Vercel : sur Cardan, la route équivalente expire en `504` alors que le travail
   *aboutit*. Un code de retour n'y prouve donc rien — **vérifier l'état en base après
   coup**. C'est précisément pour cette raison que le chemin 1 est recommandé.

`POST /api/v1/cron/nightly` existe et fonctionne (secret `CRON_SECRET`), au cas où un cron
serait rétabli un jour. Pour l'activer, ajouter à `services/api/vercel.json` :

```json
"crons": [{ "path": "/api/v1/cron/nightly", "schedule": "0 3 * * *" }]
```

> Un cron **hebdomadaire** serait le pire des choix sur cette plateforme : l'offre gratuite
> Supabase met un projet en pause après sept jours d'inactivité, soit exactement l'intervalle
> — la démonstration se réveillerait un jour sur deux. Quotidien ou rien.

## Pas encore en place

- **Le contrôle CI** qui régénère `openapi.json` et échoue sur un diff (plan §3-A.3).
- Rien d'autre : le déploiement est fait et vérifié de bout en bout.

## Ce que le premier déploiement réel a appris

- **Aucun `rewrite` ne doit être déclaré.** Le motif repris de Cardan
  (`/api/(.*)` → `/api/index`) remplace le chemin vu par l'application : FastAPI recevait
  `/api/index` et répondait `404` sur toutes ses routes. Le preset FastAPI de Vercel route
  déjà l'intégralité des requêtes vers l'objet `app` en préservant le chemin.
- **`regions: ["fra1"]` n'est pas cosmétique.** Sans lui, le premier déploiement est parti
  en `iad1` (Washington), à côté d'une base à Francfort et d'un projet annoncé en
  hébergement UE.
- **La protection de déploiement est active par défaut** sur un projet d'équipe et couvre
  toutes les URL `*.vercel.app` : une démonstration de portfolio reste inaccessible tant
  qu'elle n'est pas levée (`ssoProtection: null` par l'API Vercel, ou dans les réglages du
  projet).
- **Le seed a demandé environ 17 minutes** contre Supabase, pour 8 217 médias — l'essentiel
  du temps part dans l'envoi des fichiers, une requête réseau par objet. À lancer avant un
  rendez-vous, jamais pendant.
- **Les 300 photos réelles arrivent avec leur OCR en attente** (`deferred` dans
  `GET /queue/stats`) : c'est la séparation des pilotes qui fonctionne comme prévu. Un
  passage de `apex.cli worker --loop` depuis un poste les traite.
