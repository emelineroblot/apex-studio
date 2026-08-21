"""Point d'entrée Vercel — expose l'application ASGI FastAPI.

Le runtime Python de Vercel importe ce module et cherche une variable nommée `app`
(ou une fonction `handler`). Le reste du code applicatif vit dans `src/apex`.

Défense en profondeur : `src/` est ajouté explicitement à `sys.path` avant l'import.
En temps normal, `pip install --no-deps -e .` (voir `AGENTS.md`) rend déjà `apex`
importable via le hook d'installation éditable de hatchling. Mais `requirements.txt`
est généré en mode empreintes (`uv export --no-dev`), qui n'accepte aucune ligne sans
hachage — donc `-e .` en est exclu et installé à part. Si cette étape séparée venait à
ne pas s'exécuter (ex. builder qui ignore un second appel `pip install`), l'import
échouerait silencieusement en production sans ce filet ; il ne coûte rien en local où
l'installation éditable fonctionne déjà.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from apex.main import app  # noqa: E402 — après l'ajustement de sys.path, volontairement

__all__ = ["app"]
