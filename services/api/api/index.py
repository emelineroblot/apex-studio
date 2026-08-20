"""Point d'entrée Vercel — expose l'application ASGI FastAPI.

Le runtime Python de Vercel importe ce module et cherche une variable nommée `app`
(ou une fonction `handler`). Le reste du code applicatif vit dans `src/apex`.
"""

from apex.main import app

__all__ = ["app"]
