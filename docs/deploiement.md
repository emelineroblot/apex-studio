# Déploiement — Apex

Environnement de démonstration **jetable** : recréable de bout en bout depuis ce dépôt et le
générateur de jeu de démo. Aucune donnée à préserver, aucune dette de migration à ménager.

> Ce document est opératoire (le *comment*). Les décisions et leurs raisons sont dans
> `docs/wiki/architecture.md` — notamment « Version Python figée à 3.12 », « Poids d'une
> fonction Vercel Python » et « Séparation des pilotes par capacité d'exécution ».

## Ce qui est déployé, et ce qui ne l'est pas

| Où | Quoi |
|---|---|
| Projet Vercel `apex-web` (root `apps/web`) | Next.js — l'interface |
| Projet Vercel `apex-api` (root `services/api`) | L'API Python et **tout le pipeline sauf l'OCR** |
| Poste de développement, à la demande | `apex.cli worker --loop` — la lecture des numéros de course |

Deux projets parce qu'un projet Vercel n'a qu'un runtime de build (plan, §3-A). Le
frontend appelle l'API par `NEXT_PUBLIC_API_BASE_URL` ; l'API n'autorise en CORS que
`WEB_ORIGIN`.

**L'OCR ne tourne pas en ligne, et c'est une décision mesurée** : le moteur pèse ~322 Mo à lui
seul, pour un plafond de 250 Mo par fonction. En ligne, un lot déposé est ingéré, daté,
rattaché à son shooting, dédoublonné et regroupé en séries — en direct. Seule la lecture du
numéro attend un worker. Le jeu de démo étant seedé avec ses rattachements OCR déjà calculés,
la démonstration est complète sans worker ; il ne sert qu'à traiter des photos ajoutées après
coup.

## Prérequis externes (à créer une fois)

1. **PostgreSQL managé, région UE** — Neon (offre gratuite) dans le plan. Récupérer l'URL de
   connexion, et la préfixer `postgresql+psycopg://` (SQLAlchemy 2 + psycopg 3).
2. **Stockage objet compatible S3, juridiction UE** — Cloudflare R2 dans `.env.example`.
   Un bucket, une paire de clés d'accès.

Rien d'autre : aucune intégration tierce, c'est un invariant du projet.

## Variables d'environnement

`services/api/.env.example` fait foi pour la liste complète. Sur le projet `apex-api` :

| Variable | Valeur en démonstration |
|---|---|
| `APP_ENV` | `production` (ou n'importe quoi sauf `local`) |
| `DATABASE_URL` | l'URL Neon, en `postgresql+psycopg://…` |
| `JWT_SECRET`, `WORKER_SECRET`, `CRON_SECRET` | **trois valeurs aléatoires distinctes** |
| `DEMO_OWNER_PASSWORD`, `DEMO_PHOTOGRAPHER_PASSWORD` | à choisir — ils sont publiés par `GET /demo/accounts` |
| `STORAGE_BACKEND` | `s3` |
| `S3_ENDPOINT_URL`, `S3_REGION`, `S3_BUCKET`, `S3_ACCESS_KEY_ID`, `S3_SECRET_ACCESS_KEY` | le bucket R2 |
| `WEB_ORIGIN`, `PUBLIC_WEB_BASE_URL` | l'URL du projet `apex-web` |

Sur le projet `apex-web` : `NEXT_PUBLIC_API_BASE_URL` (URL de `apex-api`, **sans** `/api/v1`)
et `NEXT_PUBLIC_API_MODE=live`.

⚠️ `APP_ENV` vaut `production` par défaut **volontairement** : l'application refuse de démarrer
si un secret a encore sa valeur du dépôt. Le dépôt est public, ces valeurs sont connues de
tous. Un démarrage qui échoue au déploiement avec un message clair vaut mieux qu'une démo
ouverte à quiconque lit le code.

## Procédure

```bash
# 0. Garde-fou — jamais optionnel (voir docs/wiki/pieges-projet.md)
cd services/api && bash scripts/check_prod_install.sh

# 1. Schéma et jeu de démo, poussés depuis le poste vers les ressources en ligne
export DATABASE_URL='postgresql+psycopg://…neon…'
export STORAGE_BACKEND=s3 S3_ENDPOINT_URL=… S3_BUCKET=… S3_ACCESS_KEY_ID=… S3_SECRET_ACCESS_KEY=…
uv run alembic upgrade head
uv run python -m apex.cli seed --reset      # ~7 s + le temps d'envoi des médias

# 2. Déploiement (deux projets, root dirs distincts, à lier une fois)
#    apex-api : root = services/api  |  apex-web : root = apps/web
```

Le `seed` local écrit dans la base **et** le bucket en ligne : c'est le mode opératoire normal
ici, pas un contournement. Il n'existe aucune commande de seed déclenchable depuis la
fonction déployée qui tiendrait dans son budget de temps.

## Faire tourner l'OCR pendant une démonstration

Depuis le poste, avant le rendez-vous, avec les mêmes variables qu'à l'étape 1 :

```bash
cd services/api
uv sync --extra ocr                          # une fois : le moteur n'est pas dans le jeu par défaut
uv run python -m apex.cli worker --loop
```

Le worker se connecte à la base et au stockage **en ligne** : il n'a rien de local sinon le
processus. Il traite les `ocr_media` que la fonction Vercel a laissés en file — visibles à tout
moment dans `deferred` (`GET /api/v1/queue/stats`). S'il démarre en affichant
`⚠ moteur OCR absent`, l'extra `ocr` n'est pas installé : les jobs resteront en attente.

## Pas encore en place

- **Le cron de réinitialisation nocturne.** `POST /api/v1/cron/nightly` existe mais répond
  encore `501` (jalon J3). Le bloc `crons` est donc **volontairement absent** de
  `services/api/vercel.json` : un cron déclaré vers un endpoint non implémenté ne serait qu'un
  échec quotidien silencieux. À ajouter avec son implémentation :
  `{"crons": [{"path": "/api/v1/cron/nightly", "schedule": "0 3 * * *"}]}`.
- **Le contrôle CI qui régénère `openapi.json` et échoue sur un diff** (plan §3-A.3, toujours
  à livrer).
