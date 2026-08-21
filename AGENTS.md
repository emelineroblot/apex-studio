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
uv sync
uv run alembic upgrade head
uv run uvicorn apex.main:app --reload --port 8000
uv run python -m apex.cli worker --loop     # worker : boucle de drainage
uv run python -m apex.cli worker --once     # un seul tick (utilisé en serverless)
uv run python -m apex.cli seed --reset      # régénère le jeu de démo (déterministe, ~7 s)
uv run python -m apex.cli reindex           # reconstruit media_search pour tout le catalogue
uv run pytest -q
uv run ruff check . && uv run ruff format --check . && uv run mypy src
uv export --no-dev --format requirements-txt > requirements.txt
```

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

## Jalons

| Jalon | Branche | Contenu |
|---|---|---|
| J1 | `feature/socle-ingestion` | Modèle de données, auth, client / shooting / engagements, upload, EXIF, doublons, intégrité |
| J2 | `feature/ocr-recherche` | OCR, seuils, file de validation, recherche à facettes, collections |
| J3 | `feature/espace-client` | Espace client, sélection, livraison HD, devis, facture, dashboard |
