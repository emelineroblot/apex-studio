"""Hash perceptuel et netteté (§3-G.2, §3-G.3) — DCT maison en numpy, **zéro dépendance
ajoutée** (pas `scipy`/`imagehash`, hors budget des 250 Mo décompressés d'une fonction
Vercel, §3-G.2 Option 1 rejetée). Calculé sur la vignette 320 px, pas le HD.
"""

from __future__ import annotations

import numpy as np
from PIL import Image

PHASH_SIZE = 32
PHASH_LOW_FREQ = 8


def _dct_matrix(n: int) -> np.ndarray:
    """Matrice de la DCT-II orthonormée `n×n` — `dct2d = C @ x @ C.T`."""
    k = np.arange(n).reshape(-1, 1)
    nvec = np.arange(n).reshape(1, -1)
    matrix = np.cos(np.pi / n * (nvec + 0.5) * k)
    matrix *= np.sqrt(2.0 / n)
    matrix[0, :] *= 1.0 / np.sqrt(2.0)
    return matrix


_DCT_32 = _dct_matrix(PHASH_SIZE)


def to_grayscale_array(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L"), dtype=np.float64)


def compute_phash(gray: np.ndarray) -> int:
    """pHash 64 bits (§3-G.2, Option 2) : DCT-II 32×32 → bloc basses fréquences 8×8 →
    seuillage par médiane (DC exclu du calcul de la médiane, méthode standard).
    """
    small = Image.fromarray(gray.astype(np.uint8)).resize(
        (PHASH_SIZE, PHASH_SIZE), Image.Resampling.LANCZOS
    )
    pixels = np.asarray(small, dtype=np.float64)
    dct = _DCT_32 @ pixels @ _DCT_32.T
    block = dct[:PHASH_LOW_FREQ, :PHASH_LOW_FREQ].flatten()

    median = float(np.median(block[1:]))  # exclut le coefficient DC (composante continue)
    bits = (block > median).astype(np.uint64)

    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    return value


UINT64_MASK = (1 << 64) - 1


def to_signed_bigint(value: int) -> int:
    """`phash` est calculé comme un entier **non signé** 64 bits, mais `BIGINT` PostgreSQL
    est signé — sans cette conversion (two's complement), toute valeur ≥ 2^63 lève
    `NumericValueOutOfRange` à l'écriture (reproduit en conditions réelles).
    """
    value &= UINT64_MASK
    if value >= 1 << 63:
        value -= 1 << 64
    return value


def hamming_distance(a: int, b: int) -> int:
    # Masqué sur 64 bits : `a`/`b` peuvent être des `BIGINT` signés relus depuis la base
    # (donc négatifs en Python) — le masque restitue le motif de bits correct avant XOR.
    return bin((a ^ b) & UINT64_MASK).count("1")


def compute_sharpness(gray: np.ndarray) -> float:
    """Variance du Laplacien (§3-G.3) — 5 lignes, aucune dépendance (pas de `cv2`/`scipy`).

    Laplacien discret via décalages (`np.roll`) : les bords sont retirés après coup pour
    éviter l'artefact de repliement (`roll` est circulaire).
    """
    laplacian = (
        -4.0 * gray
        + np.roll(gray, 1, axis=0)
        + np.roll(gray, -1, axis=0)
        + np.roll(gray, 1, axis=1)
        + np.roll(gray, -1, axis=1)
    )
    trimmed = laplacian[1:-1, 1:-1]
    if trimmed.size == 0:
        return 0.0
    return float(np.var(trimmed))
