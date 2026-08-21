"""CLI Apex (`python -m apex.cli`, §3-A.4 et §3-E.7 du plan).

Deux pilotes du même moteur `queue.runner.drain()` :
- `worker --loop` : boucle locale (dev), dort 500 ms quand la file est vide, tourne
  jusqu'à interruption (`Ctrl+C`) — jamais de poll indéfini en `PENDING` sans sommeil.
- `worker --once` : un seul passage borné dans le temps (`--budget-seconds`), c'est le
  mode qu'appellera l'équivalent serverless (`POST /jobs/tick`, à câbler au lot suivant).

`seed --reset` régénère le jeu de démo (§3-N.1, `apex.demo.seed.run_seed`, graine fixe) et
`reindex` reconstruit `media_search` en une seule requête (`services/search_projection.py`,
§3-K) — les deux tournent hors file, en direct, pour rester des commandes scriptables sans
worker qui tourne.
"""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

import typer

# Importer le paquet des handlers charge leurs `@handler(...)` dans le registre — vide
# pour l'instant, mais l'import doit rester en place pour que les lots suivants n'aient
# rien d'autre à faire que d'ajouter leur module sous `apex/queue/handlers/`.
import apex.queue.handlers  # noqa: F401
from apex.config import settings
from apex.db import SessionLocal
from apex.queue.runner import DEFAULT_BATCH_SIZE, drain

app = typer.Typer(help="CLI Apex — worker de la file de tâches (§3-E du plan).")
# Sous-app dédiée : garantit que l'invocation reste `apex.cli worker --loop|--once`
# (§3-A.4) même si `worker` est aujourd'hui la seule commande — un `Typer` à commande
# unique collapse sinon le nom de la commande (comportement Click/Typer standard).
worker_app = typer.Typer(help="Pilotes du moteur de drainage (`queue.runner.drain`).")
app.add_typer(worker_app, name="worker")

IDLE_SLEEP_SECONDS = 0.5
DEFAULT_ONCE_BUDGET_SECONDS = 240.0


def _worker_id() -> str:
    """Identifiant du worker courant — distingue les workers dans `job.locked_by`."""
    return f"cli-{uuid.uuid4().hex[:12]}"


@worker_app.callback(invoke_without_command=True)
def worker(
    loop: bool = typer.Option(
        False, "--loop", help="Boucle locale : draine en continu, dort 500 ms à vide."
    ),
    once: bool = typer.Option(
        False, "--once", help="Un seul passage, borné par --budget-seconds, puis quitte."
    ),
    batch_size: int = typer.Option(
        DEFAULT_BATCH_SIZE, "--batch-size", help="Nombre de jobs réclamés par lot."
    ),
    budget_seconds: float = typer.Option(
        DEFAULT_ONCE_BUDGET_SECONDS,
        "--budget-seconds",
        help="Budget de temps pour --once (mime le maxDuration=300 s serverless).",
    ),
) -> None:
    """Draine la file de tâches — voir `--loop` et `--once`."""
    if loop == once:
        raise typer.BadParameter("Choisir exactement un mode : --loop ou --once.")

    worker_id = _worker_id()

    if once:
        deadline = datetime.now(UTC) + timedelta(seconds=budget_seconds)
        result = drain(SessionLocal, worker_id, deadline=deadline, batch_size=batch_size)
        typer.echo(
            f"[{worker_id}] once : claimed={result.claimed} done={result.done} "
            f"failed={result.failed} dead={result.dead} requeued={result.requeued} "
            f"reaped={result.reaped} remaining={result.remaining}"
        )
        return

    typer.echo(f"[{worker_id}] boucle locale — Ctrl+C pour arrêter.")
    try:
        while True:
            result = drain(SessionLocal, worker_id, deadline=None, batch_size=batch_size)
            if result.claimed:
                typer.echo(
                    f"[{worker_id}] tick : claimed={result.claimed} done={result.done} "
                    f"failed={result.failed} dead={result.dead} requeued={result.requeued} "
                    f"remaining={result.remaining}"
                )
            else:
                time.sleep(IDLE_SLEEP_SECONDS)
    except KeyboardInterrupt:
        typer.echo(f"[{worker_id}] arrêt demandé.")


@app.command("fetch-models")
def fetch_models(
    destination: str = typer.Option(
        None,
        "--dest",
        help="Répertoire cible (défaut : OCR_MODEL_DIR, cf. .env).",
    ),
) -> None:
    """Matérialise les poids ONNX du moteur OCR dans `OCR_MODEL_DIR` (§3-J.1).

    **Aucun téléchargement** : les poids voyagent avec la roue `rapidocr-onnxruntime`
    installée par `uv sync`. Cette commande ne fait que les recopier, pour un déploiement
    qui préfère les servir depuis un répertoire à lui. L'invariant du projet — « aucune
    intégration tierce, la démo ne doit pas pouvoir tomber à cause d'un service externe » —
    interdit une récupération réseau, même au build.
    """
    from apex.pipeline.ocr.engine import copy_bundled_models

    target = destination or settings.ocr_model_dir
    copied = copy_bundled_models(target)
    if not copied:
        typer.echo(f"Aucun poids trouvé à recopier vers {target}.")
        raise typer.Exit(code=1)
    typer.echo(f"{len(copied)} poids copiés vers {target} : {', '.join(copied)}")


@app.command("seed")
def seed(
    reset: bool = typer.Option(
        False, "--reset", help="Truque et régénère le jeu de démo (sinon no-op si déjà peuplé)."
    ),
) -> None:
    """Régénère le jeu de démo (§3-N.1) — déterministe, graine fixe.

    Hors file : appelée en direct, dans **une seule transaction** (Décision N.2, « soit
    tout est restauré, soit rien ne bouge »). Le job `demo_reset` (`POST /demo/seed`, cron
    nocturne J3) appelle exactement la même fonction.
    """
    from apex.db import session_scope
    from apex.demo.seed import run_seed

    with session_scope() as db:
        result = run_seed(db, reset=reset)

    if not result.ran:
        typer.echo("Jeu de démo déjà peuplé — no-op (utiliser --reset pour régénérer).")
        return
    typer.echo(
        f"Seed terminé en {result.duration_ms} ms : {result.simulated_media} médias simulés, "
        f"{result.real_media} médias réels, {result.shootings} shootings, "
        f"{result.engagements} engagements. Répartition : {result.attachment_status_counts}"
    )
    if result.real_photos_skipped_reason:
        typer.echo(f"Photos réelles : {result.real_photos_skipped_reason}")


@app.command("reindex")
def reindex() -> None:
    """Reconstruit `media_search` pour **tout** le catalogue (§3-K du plan).

    Une seule requête `INSERT … SELECT … ON CONFLICT DO UPDATE` — la même que la
    réindexation incrémentale déclenchée à chaque changement de rattachement.
    """
    from apex.db import session_scope
    from apex.services.search_projection import project_media_search

    started = time.monotonic()
    with session_scope() as db:
        touched = project_media_search(db, None)
    elapsed_ms = int((time.monotonic() - started) * 1000)
    typer.echo(f"Réindexation complète : {touched} médias, {elapsed_ms} ms.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
