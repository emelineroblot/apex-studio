"""Capacités d'exécution du **processus courant** — ce que ce pilote sait faire.

Le projet a un seul moteur de drainage (`queue.runner.drain`) et quatre pilotes (CLI
`worker`, `POST /jobs/tick`, ticks courts depuis `/batches` et `/cameras`). Depuis la
préparation du déploiement, ces pilotes ne tournent plus tous dans le même environnement :
la fonction Vercel n'embarque **pas** le moteur OCR (extra `ocr` de `pyproject.toml`, ~322 Mo,
plus que le plafond entier de 250 Mo — voir `docs/wiki/architecture.md`, « Poids d'une
fonction Vercel Python »). Un même `drain()` s'exécute donc dans deux environnements aux
capacités différentes.

**Détecté, jamais configuré.** La capacité est déduite de ce qui est réellement importable
(`importlib.util.find_spec`), pas d'une variable d'environnement à positionner au
déploiement. Une variable oubliée redonnerait exactement le bug qu'on veut éviter — la
fonction en ligne réclamant un job qu'elle ne peut pas exécuter — et le projet a déjà payé
une fois le prix d'un garde-fou inopérant par défaut (`APP_ENV`, § « Authentification,
cloisonnement et garde-fou de secrets »). Ici, l'installation *est* la configuration.

Le module n'est pas importé : seule sa présence est vérifiée. `find_spec` ne charge rien —
importer `rapidocr_onnxruntime` coûte ~0,4 s et de la mémoire, ce que le chemin chaud du
worker n'a aucune raison de payer à chaque `drain()`.
"""

from __future__ import annotations

import importlib.util
from functools import cache

#: Le moteur OCR (`rapidocr-onnxruntime`) est installé et importable — extra `ocr`.
OCR_ENGINE = "ocr_engine"

#: Capacité → module dont la présence en atteste. Une capacité par contrainte réelle
#: d'installation, jamais par confort : chaque entrée ici rend un type de job
#: potentiellement non réclamable, ce qui doit rester une décision explicite.
_CAPABILITY_MODULES: dict[str, str] = {OCR_ENGINE: "rapidocr_onnxruntime"}


@cache
def available_capabilities() -> frozenset[str]:
    """Capacités réellement disponibles dans ce processus. Mise en cache : l'ensemble des
    paquets installés ne change pas pendant la vie d'un worker."""
    found = set()
    for capability, module_name in _CAPABILITY_MODULES.items():
        try:
            spec = importlib.util.find_spec(module_name)
        except (ImportError, ValueError):
            # `find_spec` lève si un paquet parent est lui-même introuvable ou mal
            # installé — indiscernable d'une absence pure, et traité comme telle.
            spec = None
        if spec is not None:
            found.add(capability)
    return frozenset(found)


def missing_capabilities() -> frozenset[str]:
    """Capacités connues mais absentes ici — matière à avertissement, jamais à exception."""
    return frozenset(_CAPABILITY_MODULES) - available_capabilities()


def reset_cache_for_tests() -> None:
    """Réservé aux tests : oublie la détection mise en cache."""
    available_capabilities.cache_clear()
