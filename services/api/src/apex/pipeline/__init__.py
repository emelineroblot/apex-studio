"""Pipeline d'ingestion (§3-F du plan) — étapes déterministes, chacune traduite en état
explicite (quarantaine motivée, bac « à rattacher », etc.), jamais une exception non
gérée qui remonterait silencieusement (voir `.claude/instructions/worker-queue.instructions.md`).
"""
