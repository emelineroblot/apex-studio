# Évaluation offline de l'OCR — jeu synthétique

> Rapport **généré** par `uv run pytest -m ocr_eval`. Ne pas éditer à la main : toute modification est écrasée à la prochaine exécution.

- Généré le : 2026-08-21 02:59 UTC
- Jeu : 360 images synthétiques, 6 niveaux, graine fixe
- Table des engagements simulée : **44 voitures au départ** — paramètre décisif, cf. « Limites »
- Seuils évalués : `ocr_high = 0.85`, `ocr_low = 0.45`
- Cible bloquante : précision ≥ 98 % dans la bande « auto »

## Résultat aux seuils par défaut

| Indicateur | Valeur |
|---|---|
| Rattachement automatique | 56.9 % des images |
| **Précision dans la bande auto** | **98.0 %** |
| **Taux d'erreur parmi les rattachements auto** | **2.0 %** |
| Envoyé en validation humaine | 8.3 % (30) |
| Numéro lu hors table des engagements (incohérence) | 17.5 % (63) |
| Abstention (score sous le seuil bas) | 3.1 % (11) |
| Aucune lecture exploitable | 14.2 % (51) |

## Par niveau de difficulté

| Niveau | Auto | Précision auto | Validation | Incohérence | Abstention | Rien lu |
|---|---|---|---|---|---|---|
| 0 — studio | 85.0 % | 100.0 % | 1 | 0 | 0 | 8 |
| 1 — propre | 83.3 % | 100.0 % | 3 | 1 | 0 | 6 |
| 2 — piste | 83.3 % | 100.0 % | 1 | 3 | 1 | 5 |
| 3 — vitesse | 73.3 % | 97.7 % | 5 | 3 | 3 | 5 |
| 4 — difficile | 15.0 % | 77.8 % | 14 | 28 | 2 | 7 |
| 5 — limite | 1.7 % | 0.0 % | 6 | 28 | 5 | 20 |

## Calibration — score annoncé vs justesse observée

Le score affiché dans l'UI doit vouloir dire quelque chose. Lecture : parmi les candidats dont le numéro figure au plateau, part de lectures exactes par tranche.

| Tranche de score | Candidats | Justesse observée |
|---|---|---|
| [0.0 – 0.1[ | 0 | n/a |
| [0.1 – 0.2[ | 16 | 0.0 % |
| [0.2 – 0.3[ | 33 | 0.0 % |
| [0.3 – 0.4[ | 3 | 33.3 % |
| [0.4 – 0.5[ | 4 | 25.0 % |
| [0.5 – 0.6[ | 2 | 50.0 % |
| [0.6 – 0.7[ | 6 | 33.3 % |
| [0.7 – 0.8[ | 11 | 81.8 % |
| [0.8 – 0.9[ | 15 | 93.3 % |
| [0.9 – 1.0[ | 199 | 98.0 % |

## Balayage du seuil haut

`ocr_low` fixé à 0.45. On cherche la **couverture maximale sous contrainte de précision ≥ 98 %** — jamais l'inverse.

| `ocr_high` | Auto | Précision auto | Erreurs auto | Tient la cible |
|---|---|---|---|---|
| 0.50 | 64.7 % | 94.85 % | 12 | non |
| 0.55 | 64.4 % | 95.26 % | 11 | non |
| 0.60 | 64.2 % | 95.24 % | 11 | non |
| 0.65 | 63.9 % | 95.65 % | 10 | non |
| 0.70 | 62.5 % | 96.89 % | 7 | non |
| 0.75 | 60.8 % | 96.80 % | 7 | non |
| 0.80 | 59.4 % | 97.66 % | 5 | non |
| 0.85 | 56.9 % | 98.05 % | 4 | oui |
| 0.90 | 55.3 % | 97.99 % | 4 | non |
| 0.95 | 53.3 % | 98.44 % | 3 | oui |
| 1.00 | 0.0 % | 100.00 % | 0 | oui |

**Couple recommandé sur ce jeu : `ocr_high = 0.85`, `ocr_low = 0.45`** — 56.9 % d'automatique à 98.0 % de précision.

⚠️ **La colonne de précision n'est pas monotone, et c'est attendu.** Relever le seuil retire d'abord des lectures justes : sur 205 rattachements automatiques, une seule erreur pèse 0.49 point. L'intervalle de confiance à 95 % autour de la précision mesurée vaut environ ±1.9 point(s) — le seuil recommandé est un **ordre de grandeur**, pas une valeur à trois décimales. Agrandir le jeu (`OCR_EVAL_PER_LEVEL`) resserre l'estimation.

## Les erreurs, une par une

Ce sont les cas qui coûtent cher : une photo rattachée au mauvais engagement part chez le mauvais client. On les liste plutôt que de les résumer.

| Image | Niveau | Numéro réel | Numéro rattaché |
|---|---|---|---|
| `L3_0018.jpg` | 3 | 98 | 86 |
| `L4_0000.jpg` | 4 | 313 | 13 |
| `L4_0017.jpg` | 4 | 313 | 13 |
| `L5_0052.jpg` | 5 | 869 | 86 |

## Limites — à lire avant de citer un chiffre

- **Jeu synthétique.** Numéros rendus par code sur une carrosserie stylisée. Les photos réelles apportent reflets, salissures, angles extrêmes et lettrages publicitaires bien plus variés. Ces chiffres sont un plancher de sanité, pas une prédiction.
- **Les seuils calibrés ici ne seront pas les bons sur photos réelles.** C'est prévu : ils vivent en base (`app_setting`), se changent depuis l'UI, et leur changement re-projette les candidats existants **sans relancer aucune inférence**.
- **Protocole de recalibrage** : `OCR_EVAL_DATASET=/chemin/vers/jeu-reel uv run pytest -m ocr_eval -s`, lire le couple recommandé ci-dessus, le saisir dans `/settings/ocr`. Aucune ligne de code à modifier.
- **Ce que le taux d'abstention veut dire** : le système renonce plutôt que de deviner. Une abstention coûte un clic ; un faux positif coûte une photo livrée au mauvais client. Le déséquilibre est assumé et c'est lui qui pilote la calibration.
