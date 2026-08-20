"""Utilitaires communs aux routeurs — squelettes du lot 0 (§4, plan, Lot 0).

Chaque route existe, est typée et documentée : l'OpenAPI généré ici est le contrat gelé
que consomme le frontend (`npm run gen:api`). Le corps métier arrive aux lots suivants ;
`not_implemented()` centralise la réponse `501` pour que ce soit visible et homogène.
"""

from typing import NoReturn

from fastapi import HTTPException
from fastapi.security import HTTPBearer

# Déclaré uniquement pour que l'OpenAPI documente le schéma de sécurité `Authorization:
# Bearer <jwt>` (§3-I du plan). La vérification réelle du jeton arrive au Lot 1
# (`apex/security.py`) — `auto_error=False` pour ne pas bloquer les squelettes en 403
# avant que la logique existe.
bearer_scheme = HTTPBearer(auto_error=False)


def not_implemented(feature: str) -> NoReturn:
    """Réponse `501` uniforme pour un endpoint dont le contrat est gelé mais pas la logique."""
    raise HTTPException(
        status_code=501,
        detail={
            "code": "not_implemented",
            "message": f"« {feature} » n'est pas encore implémenté.",
            "detail": None,
        },
    )
