#!/usr/bin/env bash
# Garde-fou de déploiement — vérifie que `requirements.txt` s'installe RÉELLEMENT en
# production (Linux, la version de Python figée par `pyproject.toml`), et mesure le
# poids décompressé contre le plafond de 250 Mo d'une fonction Vercel Python.
#
# Pourquoi ce script existe (docs/wiki/pieges-projet.md, entrée 2026-08-21) : deux
# jalons complets et plusieurs revues se sont succédé sans que personne ne remarque que
# le projet ne s'installait pas en production — `rapidocr-onnxruntime` (moteur OCR,
# §Décision J) n'a jamais publié de version compatible Python 3.13, et `uv sync` en
# local ne le signale pas (contrairement à `pip`, qu'utilise le builder Vercel). `uv
# run`/`uv sync` valident un environnement de DÉVELOPPEMENT ; rien ne validait
# l'installation de PRODUCTION avant ce script.
#
# Usage (depuis `services/api`) :
#   bash scripts/check_prod_install.sh
#
# Prérequis : Docker. Ne touche jamais au `.venv` local ni au conteneur Postgres de
# développement — tout se passe dans un conteneur jetable.

set -euo pipefail

# Git Bash sur Windows réinterprète les chemins façon `/app` comme des chemins Windows
# avant de les passer à `docker` — sans effet sur Linux/macOS, où cette variable est
# simplement ignorée par un docker natif.
export MSYS_NO_PATHCONV=1

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
API_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${API_DIR}"

# `docker -v` sous Docker Desktop (Git Bash) exige un chemin Windows natif (`D:\...`),
# pas le chemin POSIX que bash manipule (`/d/...`) — `cygpath` fait la conversion ;
# absent sur Linux/macOS, où le chemin POSIX est déjà celui qu'attend un docker natif.
to_docker_path() {
  if command -v cygpath >/dev/null 2>&1; then
    cygpath -w "$1"
  else
    printf '%s' "$1"
  fi
}
API_DIR_DOCKER="$(to_docker_path "${API_DIR}")"

# Doit rester aligné sur `requires-python` dans pyproject.toml (borne haute) — pas
# déduit automatiquement pour que toute dérive de version soit un diff visible ici.
PYTHON_IMAGE="python:3.12-slim"
WEIGHT_BUDGET_MB=250

echo "== [1/4] requirements.txt s'installe-t-il par pip seul (mode empreintes) ? =="
if grep -qE '^-e ' requirements.txt 2>/dev/null; then
  echo "ERREUR : requirements.txt contient une ligne '-e .' — casse le mode empreintes" \
       "de pip dès qu'une seule autre ligne porte un hachage (cas de ce fichier)." >&2
  echo "Le paquet local doit être exclu de l'export (uv export --no-emit-project) et" \
       "installé séparément, voir étape [2/4] et AGENTS.md." >&2
  exit 1
fi
if ! head -n1 requirements.txt | grep -qE '^(#|[a-zA-Z0-9_.-]+==)'; then
  echo "ERREUR : la première ligne de requirements.txt n'est ni un commentaire ni une" \
       "dépendance épinglée — probablement un message de statut uv capturé par erreur" \
       "(voir AGENTS.md, commande d'export)." >&2
  echo "Ligne 1 actuelle : $(head -n1 requirements.txt)" >&2
  exit 1
fi

# Le moteur OCR est un extra optionnel (`[project.optional-dependencies] ocr`) : sa
# fermeture pèse ~322 Mo, plus que le plafond entier. S'il réapparaît dans
# `requirements.txt` (export lancé avec `--extra ocr`, ou dépendance remise en principale),
# le déploiement dépasse forcément — autant le dire ici plutôt qu'après 4 minutes de mesure.
if grep -qiE '^(rapidocr-onnxruntime|onnxruntime|opencv-python(-headless)?)==' requirements.txt; then
  echo "ERREUR : requirements.txt embarque le moteur OCR ou sa fermeture (rapidocr/onnxruntime/opencv)." >&2
  echo "La fonction Vercel ne doit jamais l'installer — il est réservé au worker local"        "(extra 'ocr'). Régénérer sans --extra : uv export --no-dev --format requirements-txt"        "--no-emit-project > requirements.txt" >&2
  exit 1
fi

WORK=$(mktemp -d)
trap 'rm -rf "${WORK}"' EXIT
WORK_DOCKER="$(to_docker_path "${WORK}")"

docker run --rm \
  -v "${API_DIR_DOCKER}:/app:ro" \
  -v "${WORK_DOCKER}:/out" \
  -w /app \
  -e APP_ENV=local \
  -e JWT_SECRET=check-prod-install \
  -e WORKER_SECRET=check-prod-install \
  "${PYTHON_IMAGE}" bash -c '
    set -euo pipefail
    python -m venv /venv >/dev/null
    /venv/bin/pip install --no-cache-dir --upgrade pip -q

    echo "== [2/4] installation en deux temps (hash-checked + paquet local --no-deps) =="
    /venv/bin/pip install --no-cache-dir -r requirements.txt -q

    # `opencv-python` (tiré par rapidocr-onnxruntime) embarque les bibliothèques GTK/Qt
    # dont un serveur n'\''a aucun usage. Substitution par la variante headless, MÊME
    # version exacte (pas de dérive de comportement) — impossible via
    # `[tool.uv.override-dependencies]`, qui ne fait que réviser une contrainte de
    # version, jamais remplacer un nom de paquet par un autre. `pip uninstall` puis
    # `install` (plutôt qu'\''une simple installation par-dessus) pour ne laisser aucun
    # fichier orphelin de la variante GUI sur le disque.
    # `|| true` indispensable : depuis que le moteur OCR est un extra optionnel (absent de
    # requirements.txt), `pip show opencv-python` échoue — et sous `set -euo pipefail` cet
    # échec, avalé par `2>/dev/null`, tuait le script entier sans un mot juste après avoir
    # affiché le message « [2/4] ». Le cas nominal est désormais « opencv absent ».
    OPENCV_VERSION=$(/venv/bin/pip show opencv-python 2>/dev/null | awk "/^Version:/ {print \$2}" || true)
    if [ -n "${OPENCV_VERSION}" ]; then
      echo "   opencv-python==${OPENCV_VERSION} -> opencv-python-headless==${OPENCV_VERSION}"
      /venv/bin/pip uninstall -y -q opencv-python
      /venv/bin/pip install --no-cache-dir --no-deps -q "opencv-python-headless==${OPENCV_VERSION}"
    fi

    /venv/bin/pip install --no-cache-dir --no-deps -e . -q

    echo "== [3/4] l'\''application importe-t-elle sans le .pth d'\''installation éditable ? =="
    # Contrôle le plus strict : désinstalle le paquet local et compte UNIQUEMENT sur le
    # filet sys.path d'\''api/index.py (voir sa docstring). Si ceci casse, la production
    # casserait aussi au cas où le builder Vercel ignore la seconde installation pip.
    /venv/bin/pip uninstall -y -q apex-api || true
    cd /app && /venv/bin/python api/index.py >/dev/null 2>&1 || true
    /venv/bin/python -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path(\"/app/src\")))
from apex.main import app
print(\"IMPORT_OK:\", app.title)
"
    # Réinstalle pour la mesure de poids (état représentatif du déploiement réel).
    /venv/bin/pip install --no-cache-dir --no-deps -e . -q

    echo "== [4/4] poids décompressé =="
    SITE_PACKAGES=$(/venv/bin/python -c "import sysconfig; print(sysconfig.get_paths()[\"purelib\"])")
    du -sh "${SITE_PACKAGES}" | tee /out/weight.txt
    du -sh "${SITE_PACKAGES}"/* 2>/dev/null | sort -rh | head -20 | tee /out/breakdown.txt
    # `pip` lui-même (outil de build, pas dépendance runtime) fausse la mesure à la
    # hausse — soustrait pour approcher le poids réellement déployé.
    /venv/bin/python -c "
import pathlib, subprocess
sp = pathlib.Path(\"${SITE_PACKAGES}\")
total = sum(f.stat().st_size for f in sp.rglob(\"*\") if f.is_file())
pip_dir = sp / \"pip\"
pip_size = sum(f.stat().st_size for f in pip_dir.rglob(\"*\") if f.is_file()) if pip_dir.exists() else 0
mb = (total - pip_size) / 1_000_000
print(f\"{mb:.1f}\")
" > /out/weight_mb_excl_pip.txt
  '

WEIGHT_MB=$(cat "${WORK}/weight_mb_excl_pip.txt")
echo ""
echo "== Résumé =="
echo "Poids décompressé (hors pip, build-only) : ${WEIGHT_MB} Mo — plafond Vercel : ${WEIGHT_BUDGET_MB} Mo"

if awk -v w="${WEIGHT_MB}" -v b="${WEIGHT_BUDGET_MB}" 'BEGIN { exit !(w > b) }'; then
  echo "ÉCHEC : dépassement de $(awk -v w="${WEIGHT_MB}" -v b="${WEIGHT_BUDGET_MB}" 'BEGIN { printf "%.1f", w - b }') Mo." >&2
  echo "Voir docs/wiki/architecture.md (« Version Python figée... ») pour le contexte" \
       "et les pistes de réduction déjà explorées." >&2
  exit 1
fi

echo "OK — sous le plafond."
