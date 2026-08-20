"""File de tâches en table PostgreSQL (§3-E du plan) — pièce technique centrale du projet.

Ce paquet ne contient **aucune logique métier** : les handlers réels (`ingest_media`,
`finalize_batch`, l'OCR, …) arrivent aux lots suivants et s'enregistrent dans
`queue.registry`. Ici : réclamation atomique, cycle de vie, reprise après crash,
drainage — le moteur, pas ce qu'il exécute.
"""
