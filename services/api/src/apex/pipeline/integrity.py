"""Contrôle d'intégrité (§3-F.1, étape 2) — fichier tronqué, format inattendu, dimensions
aberrantes → motif de quarantaine lisible. Ne lève jamais : le résultat est toujours un
`IntegrityResult`, exploité par l'appelant pour décider quarantaine ou suite du pipeline.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any

from PIL import Image, UnidentifiedImageError

MIN_DIMENSION_PX = 640
MAX_DIMENSION_PX = 12000
MIN_ASPECT_RATIO = 0.2
MAX_ASPECT_RATIO = 5.0


@dataclass(slots=True)
class IntegrityResult:
    ok: bool
    reason: str | None = None
    detail: dict[str, Any] = field(default_factory=dict)
    width: int | None = None
    height: int | None = None
    mime: str | None = None


def check_integrity(data: bytes) -> IntegrityResult:
    if not data:
        return IntegrityResult(ok=False, reason="truncated_file", detail={"byte_size": 0})

    # `Image.verify()` détecte la plupart des fichiers tronqués/corrompus, mais invalide
    # l'objet pour tout usage ultérieur — on rouvre pour un décodage réel complet, qui
    # attrape les corruptions que `verify()` seul laisse passer (§3-F.1).
    # 🟡 : `Image.DecompressionBombError` hérite d'`Exception`, pas d'`OSError` — absente
    # des tuples ci-dessous, elle se serait échappée de cette fonction (« ne lève jamais »
    # rompu). `MAX_DIMENSION_PX` (144 MPx) dépasse le seuil par défaut de Pillow (~89 MPx) :
    # une image dans notre plage de dimensions acceptée peut malgré tout déclencher ce
    # garde-fou-là.
    try:
        with Image.open(io.BytesIO(data)) as probe:
            probe.verify()
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        return IntegrityResult(ok=False, reason="not_an_image", detail={})

    try:
        with Image.open(io.BytesIO(data)) as img:
            img.load()  # décodage réel — lève sur un flux tronqué en plein milieu des données
            fmt = img.format
            width, height = img.size
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        return IntegrityResult(ok=False, reason="truncated_file", detail={"error": str(exc)})

    if fmt != "JPEG":
        return IntegrityResult(
            ok=False,
            reason="unsupported_mime",
            detail={"format": fmt},
            width=width,
            height=height,
        )

    if (
        width < MIN_DIMENSION_PX
        or height < MIN_DIMENSION_PX
        or width > MAX_DIMENSION_PX
        or height > MAX_DIMENSION_PX
    ):
        return IntegrityResult(
            ok=False,
            reason="dimensions_out_of_range",
            detail={
                "width": width,
                "height": height,
                "expected": f"[{MIN_DIMENSION_PX}..{MAX_DIMENSION_PX}]",
            },
            width=width,
            height=height,
            mime="image/jpeg",
        )

    ratio = width / height
    if ratio < MIN_ASPECT_RATIO or ratio > MAX_ASPECT_RATIO:
        return IntegrityResult(
            ok=False,
            reason="aspect_ratio_out_of_range",
            detail={
                "ratio": round(ratio, 3),
                "expected": f"[{MIN_ASPECT_RATIO}..{MAX_ASPECT_RATIO}]",
            },
            width=width,
            height=height,
            mime="image/jpeg",
        )

    return IntegrityResult(ok=True, width=width, height=height, mime="image/jpeg")
