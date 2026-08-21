# AGENTS.md — Apex

Contexte projet portable pour tout agent de code. **Source de vérité unique** :
`CLAUDE.md` y renvoie et ne duplique rien.

## Ce qu'est ce projet

Outil interne de gestion d'un studio photo de sport mécanique. Le cœur est un **pipeline
d'ingestion de photos** : EXIF → rattachement au shooting par fenêtre temporelle → dédoublonnage →
contrôle d'intégrité → OCR du numéro de course → validation humaine. Autour : recherche à facettes,
collections, espace client externe avec sélection, et facturation issue de cette sélection.

Le cadrage complet est dans `contexte/brief-app-b-studio-photo.md` (non versionné).

> Pièce de portfolio. Studio, clients et données sont fictifs. **Aucune donnée personnelle réelle.**

## Stack

| Couche | Choix | Non négociable |
|---|---|---|
| Backend | Python | oui |
| Frontend | Next.js (App Router, TypeScript) | oui |
| Base de données | PostgreSQL | oui |
| Recherche | PostgreSQL natif (GIN, `tsvector`, facettes par agrégats) | oui — pas de moteur externe |
| Traitement asynchrone | Worker Python, file de tâches en table PostgreSQL (`FOR UPDATE SKIP LOCKED`) | oui — pas de Celery/Redis, pas d'orchestrateur |
| Stockage fichiers | Stockage objet compatible S3, hébergement UE | oui |
| Déploiement | Vercel, offre gratuite | oui |

## Règles d'architecture

- **Aucune intégration tierce.** La démo ne doit pas pouvoir tomber à cause d'un service externe.
- **L'environnement est jetable.** Recréable depuis le dépôt + le générateur de jeu de démo.
  Pas de dette de migration à préserver : si le schéma bouge fortement, on repart d'une base vierge.
- **Le pipeline ne perd jamais un fichier.** Tout média non rattaché, corrompu ou ambigu atterrit
  dans un bac explicite avec un motif lisible. Jamais de rejet silencieux.
- **L'IA propose, l'humain arbitre.** L'OCR ne rattache de force jamais rien : au-dessus du seuil
  haut il rattache, entre les deux seuils il alimente une file de validation, en dessous il s'abstient.
  Les seuils sont **configurables**, jamais codés en dur.
- **Le déterministe reste au code.** L'OCR ne fait que lire un numéro ; le rattachement
  numéro → pilote → écurie → client est une jointure SQL sur la table des engagements.
- **Un pilote ne réclame que ce qu'il sait exécuter.** Le moteur OCR est un extra optionnel
  (`uv sync --extra ocr`) : il ne tient pas dans une fonction Vercel (~322 Mo pour un plafond
  de 250). Chaque handler déclare ses capacités (`@handler(..., requires=(OCR_ENGINE,))`) et
  `drain()` détecte celles du processus courant (`queue/capabilities.py`) — **détecté depuis
  l'installation, jamais configuré par variable d'environnement**. Un pilote incapable laisse
  le job `pending` (compté dans `deferred`) pour un pilote capable ; il ne le réclame jamais
  pour l'échouer. En clair : en ligne tout le pipeline tourne sauf la lecture des numéros,
  que `uv run python -m apex.cli worker --loop` traite depuis un poste, par le réseau.
- **Un test ne remplace pas le parcours réel.** Les tests fabriquent leurs propres données ;
  la démonstration tourne sur le jeu généré. Trois écarts majeurs de ce projet n'ont été vus
  qu'en confrontant le code au réel — dont une démonstration où rien n'était livrable, avec
  303 tests verts. `python scripts/verify_j3_flow.py` rejoue le parcours complet : à passer
  à chaque jalon, avant de conclure.
- **Le HD n'est jamais servi avant validation.** Aperçus filigranés côté client, accès au stockage
  objet toujours médié par le backend.

## Modèle de données — invariants

- Un `Shooting` porte une **plage temporelle** ; c'est elle qui rattache les médias, pas un choix manuel.
- La table des **engagements** (numéro de voiture → pilote → écurie → client, *pour un shooting donné*)
  est la clé métier : un numéro seul n'a aucun sens hors de son événement.
- Un média peut être rattaché à **plusieurs** engagements (deux voitures sur la même photo).
- Une facture émise est **immuable** ; seule une facture non émise se met à jour quand la sélection change.

## Conventions

- **Langue** : code et identifiants en anglais ; commentaires, messages de commit et documentation
  en français.
- **Branches** : `main` est la seule branche longue. Un jalon = une branche `feature/<nom-court>`,
  mergée dans `main` après revue et tests. **Pas de `develop` sur ce projet** (environnement jetable,
  une seule développeuse — une branche longue de plus n'ajoute qu'un merge de plus).
- **Secrets** : via `.env`, jamais en dur, jamais committés.
- **Médias** : jamais dans le dépôt (`media/`, `uploads/`, `demo-photos/` sont gitignorés).

## Commandes

**Bases locales** (à la racine) — PostgreSQL 18, jetables :

```bash
docker compose up -d          # dev sur 55432, tests sur 55433 (tmpfs)
docker compose down -v        # tout jeter
```

**Backend** (depuis `services/api`) :

```bash
uv sync --extra ocr           # `--extra ocr` : moteur OCR, hors du jeu par défaut (voir plus bas)
uv run alembic upgrade head
uv run uvicorn apex.main:app --reload --port 8000
uv run python -m apex.cli worker --loop     # worker : boucle de drainage
uv run python -m apex.cli worker --once     # un seul tick (utilisé en serverless)
uv run python -m apex.cli seed --reset      # régénère le jeu de démo (déterministe, ~7 s)
uv run python -m apex.cli reindex           # reconstruit media_search pour tout le catalogue
uv run pytest -q
uv run pytest -m ocr_eval -s                # gate bloquant, ~5 min, voir tests/ocr/test_eval.py
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv export --no-dev --format requirements-txt --no-emit-project > requirements.txt
bash scripts/check_prod_install.sh          # garde-fou obligatoire avant tout déploiement
python scripts/verify_j3_flow.py            # parcours de bout en bout, API lancée + base seedée
                                            # (installe par pip en Linux réel, refuse le moteur
                                            # OCR dans requirements.txt, mesure le poids)
```

**Python figé à 3.12** (`pyproject.toml`, `requires-python`) — jamais 3.13 : le moteur OCR
(`rapidocr-onnxruntime`, Décision J) n'a publié aucune version compatible Python 3.13 sur PyPI,
constaté en conditions réelles (§ `docs/wiki/architecture.md`, « Version Python figée »). `uv
sync`/`uv run` ne détectent pas cette dérive — seul `pip` (utilisé par le builder Vercel) la
détecte. D'où deux règles :
- Ne jamais monter `requires-python` au-delà de `<3.13` sans revérifier cette compatibilité.
- **`uv sync`/`uv run` valident un environnement de développement, pas une installation de
  production.** `bash scripts/check_prod_install.sh` (conteneur Linux jetable, `pip` réel,
  mode empreintes) est le seul test qui valide l'installation réellement livrée à Vercel —
  à exécuter avant tout déploiement, pas seulement en cas de doute.

**`requirements.txt` : deux pièges déjà rencontrés**, tous deux capturés par
`check_prod_install.sh` :
- `uv export` sans `--no-emit-project` ajoute une ligne `-e .` **sans hachage**, qui casse le
  mode empreintes de `pip` dès qu'une autre ligne porte un hachage (le cas ici). Le paquet
  local s'installe **à part** : `pip install --no-deps -e .`.
- Toujours rediriger `uv export` avec `>` (jamais `2>&1 | ...`, qui fusionnerait le message de
  statut `uv` — écrit sur stderr — dans le fichier). Vérifier la première ligne du fichier
  généré : un commentaire `#` ou une dépendance épinglée, jamais autre chose.

**Frontend** (depuis `apps/web`) :

```bash
npm install
npm run dev / build / lint / typecheck
npm run gen:api        # types TS depuis services/api/openapi.json
npx vitest run
```

### Deux pièges d'exécution, appris à nos dépens

- **Ne jamais lancer deux `pytest` concurrents.** Il n'y a **qu'une** base de test (`55433`), et
  `conftest.py` la réinitialise par `DROP SCHEMA`. Deux exécutions simultanées s'interbloquent dans
  PostgreSQL. Si un jour plusieurs agents doivent tester en parallèle, il faudra une base (ou un
  schéma) par exécutant — pas un simple retry.
- **`openapi.json` est le contrat, et il se régénère.** Toute évolution des schémas backend doit être
  suivie d'une régénération, puis d'un `npm run gen:api` côté frontend. Un frontend qui code contre
  un contrat périmé compile parfaitement et casse en production.

## Variables d'environnement

Voir `services/api/.env.example` pour la liste complète. Deux méritent une mention :

- **`APP_ENV`** — `local` en développement, autre chose ailleurs. Le défaut est **`production`**,
  volontairement : c'est un garde-fou *fail-closed*. L'application **refuse de démarrer** si un secret
  (`JWT_SECRET`, `WORKER_SECRET`, `CRON_SECRET`, mots de passe de démo) a encore sa valeur du dépôt
  alors que `APP_ENV != local`. Le dépôt est public : ces valeurs sont connues de tous, donc forgeables.
  Un premier correctif avait fait de `local` le défaut, ce qui rendait le garde-fou inopérant
  précisément dans le cas visé — la variable oubliée au déploiement.
- **`STORAGE_BACKEND`** — `local` (écrit dans `./storage`, gitignoré) ou `s3`.

## Déploiement

Deux projets Vercel (`apex-web` = `apps/web`, `apex-api` = `services/api`) et **un projet
Supabase** (PostgreSQL + Storage), comme Cardan. L'OCR est exécuté depuis un poste par
`apex.cli worker --loop`, et la démonstration se remet à neuf à la main — **pas de cron**.

Deux chaînes de connexion, jamais interchangeables : `DATABASE_URL` (Transaction pooler,
6543) pour l'API, `DATABASE_URL_DIRECT` (Session pooler, 5432) pour Alembic. Procédure complète,
variables et limites connues : **`docs/deploiement.md`**.

## Jalons

| Jalon | Branche | Contenu |
|---|---|---|
| J1 | `feature/socle-ingestion` | Modèle de données, auth, client / shooting / engagements, upload, EXIF, doublons, intégrité |
| J2 | `feature/ocr-recherche` | OCR, seuils, file de validation, recherche à facettes, collections |
| J3 | `feature/espace-client` | Espace client, sélection, livraison HD, devis, facture, dashboard |

Les trois jalons sont livrés. Le contrat n'a plus aucune route en `501`.
