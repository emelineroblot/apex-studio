"""OCR du numéro de course (§3-J du plan) — application stricte du principe DOE.

| Couche | Module | Rôle |
|---|---|---|
| **Directives** | `apex.services.ocr_settings` | Seuils et bornes géométriques, en base |
| **Orchestration** | `engine.py` | **Le seul appel au modèle** : lire une image → textes + confiances |
| **Exécution** | `normalize.py`, `scoring.py`, `classify.py` | Tout le déterministe |

Le modèle ne décide **jamais** d'un rattachement. Il produit un texte et un nombre ; la
normalisation, le score composite, la jointure sur `engagement` et l'application des seuils
sont du code exact, testé, rejouable — et re-jouable **sans lui** (`reclassify_ocr`).
"""
