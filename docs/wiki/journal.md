---
type: journal
maj: 2026-08-21
---

# Journal des runs

## 2026-08-21 — Préparation du déploiement (`feature/preparation-deploiement`)
Livré : Python figé à 3.12, moteur OCR sorti des dépendances de production (extra `ocr`),
`scripts/check_prod_install.sh` (installation `pip` réelle en conteneur Linux + mesure de
poids), 300 photos réelles sourcées sous licences libres par un script reproductible, et la
séparation des pilotes de la file par capacité d'exécution. Paquet déployable mesuré à
**214,8 Mo pour un plafond de 250**. 232 tests verts.
Le fait notable : deux jalons complets s'étaient succédé sans que **personne n'installe jamais
le projet comme le fait la production** — `uv sync` acceptait sur Python 3.13 un moteur OCR qui
n'y a jamais eu de roue, là où `pip` refuse net. Un environnement de développement qui marche ne
dit rien d'une installation de production.
Deuxième fait notable : le garde-fou écrit pour cela s'est cassé sur le changement suivant
(`pipefail` + `pip show` d'un paquet devenu absent), et mourait sans message. Un garde-fou fait
partie du périmètre du changement qu'il garde.
Blackboard d'origine : `.agent-team/` (éphémère).
Détail : `architecture.md#version-python-figée-à-312-et-validation-dinstallation-de-production`,
`architecture.md#poids-dune-fonction-vercel-python--250-mo-mesurés-pas-supposés` et
`architecture.md#séparation-des-pilotes-par-capacité-dexécution-détectée-et-non-configurée`.

## 2026-08-21 — J2, intelligence et recherche (`feature/ocr-recherche`)
Livré : lecture du numéro de course par OCR embarqué (RapidOCR/ONNX, aucun service tiers), seuils
configurables avec re-projection des candidats bruts sans ré-inférence, file de validation
humaine, recherche à facettes et plein texte en PostgreSQL pur, collections, et un générateur de
jeu de démonstration à ~8 400 médias. 8 critères d'acceptation sur 8, 3 bloquants de revue
corrigés.
Le fait notable : la valeur du jalon n'est pas le taux d'OCR mais la **frontière DOE rendue
opposable** — le modèle ne produit qu'un texte, une confiance et un quadrilatère ; trois tests
(moteur factice, moteur qui lève, analyse d'AST) interdisent au métier d'en dépendre.
Deuxième fait notable : l'évaluation offline a corrigé le plan sur trois points, dont le plus
important est méthodologique — un jeu de test simulant un plateau de 168 voitures au lieu de 44
mesurait autre chose que le produit (92,2 % contre 98,0 %).
Blackboard d'origine : `.agent-team/` (éphémère).
Détail : `architecture.md#frontière-doe-de-locr--le-modèle-produit-un-texte-et-un-nombre-jamais-un-rattachement`,
`architecture.md#calibration-des-seuils--ce-que-lévaluation-offline-a-corrigé-du-plan` et
`architecture.md#visibilité-par-défaut-dune-liste-de-médias--une-source-unique-paramétrée-par-colonnes`.

## 2026-08-20 — J1, socle et ingestion (`feature/socle-ingestion`)
Livré : modèle de données complet des 3 jalons (28 tables, une seule révision Alembic),
authentification à deux rôles cloisonnés, CRUD référentiel et shootings, upload par lot avec
reprise, file de tâches en table PostgreSQL, pipeline d'ingestion (EXIF, rattachement temporel,
dédoublonnage exact et perceptuel, intégrité, quarantaine motivée) et 14 écrans.
Le fait notable : la revue a trouvé 7 bloquants, dont **quatre dans la file de tâches et aucun
dans le pipeline** — le maillon faible de « aucun fichier perdu » est la file, pas l'ingestion.
Deuxième fait notable : la même régression de libellé est revenue trois fois, jusqu'à ce que les
énumérations soient fermées dans le contrat OpenAPI plutôt que maintenues à la main.
Blackboard d'origine : `.agent-team/` (éphémère).
Détail : `architecture.md#non-double-traitement--réclamation-atomique-et-verrou-logique` et
`architecture.md#contrat-dapi-gelé-dans-openapijson-et-régénéré`.
