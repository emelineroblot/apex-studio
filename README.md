# Apex — outil interne de gestion d'un studio photo motorsport

Application métier de démonstration : ingérer plusieurs milliers de photos de course,
les rattacher automatiquement au bon shooting et au bon pilote, les rendre cherchables,
puis les livrer au client — dont la sélection alimente la facture.

> Pièce de portfolio. Le studio, les clients et les données sont fictifs.

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

## Stack

| Couche | Choix |
|---|---|
| Backend | Python |
| Frontend | Next.js |
| Base de données | PostgreSQL — recherche plein texte et facettes natives, pas de moteur externe |
| Traitement asynchrone | Worker Python, file de tâches en table PostgreSQL (`SKIP LOCKED`) |
| Stockage fichiers | Stockage objet compatible S3, hébergement UE |
| Déploiement | Vercel, environnement de démonstration jetable |

Aucune intégration tierce : la démo ne peut pas tomber pour une raison qui ne la concerne pas.

## Jalons

| Jalon | Branche | Contenu |
|---|---|---|
| J1 | `feature/socle-ingestion` | Modèle de données, auth, client / shooting / engagements, upload, EXIF, doublons, intégrité |
| J2 | `feature/ocr-recherche` | OCR, seuils, file de validation, recherche à facettes, collections |
| J3 | `feature/espace-client` | Espace client, sélection, livraison HD, devis, facture, dashboard |

## Workflow git

`main` est la seule branche longue. Chaque jalon vit dans une branche `feature/*`
mergée dans `main` après validation.

## Licence

Projet de démonstration, non destiné à un usage en production.
