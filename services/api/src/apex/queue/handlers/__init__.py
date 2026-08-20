"""Handlers de jobs (`ingest_media`, `finalize_batch`, `reattach_camera`, `sweep_orphans`,
puis l'OCR en J2, la livraison et le reset démo en J3, …).

Vide à ce stade — aucune logique métier dans ce lot (voir `apex/queue/registry.py`).
Chaque futur handler s'enregistre via `@handler("kind", max_attempts=...)` et **doit**
être importé ici pour que `apex.cli` le charge dans le registre au démarrage du worker.
"""
