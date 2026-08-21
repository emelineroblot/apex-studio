# Apex — outil interne de gestion d'un studio photo motorsport

Application métier de démonstration : ingérer plusieurs milliers de photos de course,
les rattacher automatiquement au bon shooting et au bon pilote, les rendre cherchables,
puis les livrer au client — dont la sélection alimente la facture.

> Pièce de portfolio. Le studio, les clients et les données sont fictifs.

**Démonstration en ligne : https://apex-web-emdigital.vercel.app** — les identifiants sont
proposés sur l'écran de connexion.

## Le problème

Un week-end de course produit 3 000 à 8 000 photos. Il faut les trier par écurie, par pilote
et par voiture, écarter les rafales et les fichiers ratés, livrer à chaque client ce qui le
concerne. Fait à la main dans un explorateur de fichiers, c'est plusieurs soirées de travail.

## Le pipeline d'ingestion

À chaque lot déposé, en tâche de fond :

1. **Upload par lot** — file d'attente visible, reprise après interruption, vignettes et aperçus
2. **EXIF** — date de déclenchement, boîtier, objectif, ISO, vitesse, ouverture, focale
3. **Rattachement au shooting** par fenêtre temporelle — l'horodatage suffit, rien à choisir
4. **Doublons** — hash exact du fichier, puis hash perceptuel pour regrouper les rafales
5. **Intégrité** — fichier tronqué, EXIF incohérent, dimensions aberrantes → quarantaine motivée
6. **OCR du numéro de course** — recoupé avec la table des engagements du shooting
   (numéro → pilote → écurie → client), avec score de confiance et seuils
7. **Validation humaine** — le photographe arbitre au clavier les seuls cas ambigus

Le modèle propose, l'humain arbitre. Le taux de rattachement automatique est un indicateur
de l'application, pas un chiffre caché.

## L'espace client

Une collection publiée se partage par un lien signé, valable quelques jours et révocable à
tout moment. Le client y trouve ses photos en aperçu filigrané, coche celles qu'il veut,
commente celles qui le méritent, puis valide.

Cette validation est le point de bascule : la sélection se fige, l'archive haute définition
se prépare, et une facture brouillon apparaît côté studio. Le client suit la préparation et
télécharge quand c'est prêt. Aucun fichier haute définition ne sort avant ce moment.

Le lien n'est affiché **qu'une fois** : la base n'en garde que l'empreinte, personne ne peut
le réafficher — pas même le studio. Et sa révocation prend effet immédiatement, pas à
l'expiration de la session en cours.

## Facturation

Une facture brouillon suit la sélection ; une facture émise ne bouge plus jamais. Ce n'est
pas une règle applicative : deux triggers PostgreSQL refusent toute modification de ses
lignes, et le retour de « émise » à « brouillon ». Trois tests attaquent la base
directement pour le prouver, un quatrième vérifie qu'un brouillon reste bien modifiable.

Un devis accepté crée le shooting correspondant, avec la même période — c'est cette période
qui rattachera automatiquement les photos du week-end.

## Stack

| Couche | Choix |
|---|---|
| Backend | Python |
| Frontend | Next.js |
| Base de données | PostgreSQL — recherche plein texte et facettes natives, pas de moteur externe |
| Traitement asynchrone | Worker Python, file de tâches en table PostgreSQL (`SKIP LOCKED`) |
| Stockage fichiers | Supabase Storage (endpoint S3-compatible), région UE |
| Déploiement | Deux projets Vercel + un projet Supabase, environnement jetable |

Aucune intégration tierce : la démo ne peut pas tomber pour une raison qui ne la concerne pas.

## Jalons

| Jalon | Branche | Contenu |
|---|---|---|
| J1 | `feature/socle-ingestion` | Modèle de données, auth, client / shooting / engagements, upload, EXIF, doublons, intégrité |
| J2 | `feature/ocr-recherche` | OCR, seuils, file de validation, recherche à facettes, collections |
| J3 | `feature/espace-client` | Espace client, sélection, livraison HD, devis, facture, dashboard |

## Vérifier que tout marche vraiment

```bash
cd services/api
uv run pytest -q                            # 303 tests
uv run python -m apex.cli seed --reset      # jeu de démonstration
uv run uvicorn apex.main:app --port 8001    # dans un autre terminal
python scripts/verify_j3_flow.py            # 34 vérifications de bout en bout
```

Le dernier script joue le parcours complet — partage, sélection, validation, archive,
facture, révocation — contre l'API réelle et les données de la démonstration. Il existe
parce que les tests, eux, fabriquent leurs propres données : c'est lui qui a révélé
qu'aucune collection du jeu de démonstration n'était livrable, alors que les 303 tests
étaient verts.

## Workflow git

`main` est la seule branche longue. Chaque jalon vit dans une branche `feature/*`
mergée dans `main` après validation.

## Licence

Projet de démonstration, non destiné à un usage en production.
