"""Handlers de jobs (`ingest_media`, `finalize_batch`, `reattach_camera`, `sweep_orphans`,
`ocr_media` et `reclassify_ocr` en J2, la livraison et le reset démo en J3, …).

Chaque handler s'enregistre via `@handler("kind", max_attempts=...)` au moment de son
import — importer ce paquet est ce qui les charge dans le registre (`apex.cli`, `main.py`
via `apex.queue.handlers`). Un module non importé ici reste invisible du worker, même s'il
définit un handler valide.
"""

from apex.queue.handlers import (  # noqa: F401 — l'import déclenche l'enregistrement
    demo_reset,
    finalize_batch,
    ingest_media,
    ocr_media,
    reattach_camera,
    reclassify_ocr,
    reindex_media,
    sweep_orphans,
)

__all__ = [
    "demo_reset",
    "finalize_batch",
    "ingest_media",
    "ocr_media",
    "reattach_camera",
    "reclassify_ocr",
    "reindex_media",
    "sweep_orphans",
]
