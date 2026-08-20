"""Générateurs d'images JPEG **réelles** pour les tests du pipeline (§4, Lot 5 du plan :
« Tests avec images réelles construites en fixture »). Construites par code plutôt que
des binaires committés — plus lisible en revue, aucun octet binaire versionné.
"""

from __future__ import annotations

import datetime
import io

import piexif
from PIL import Image, ImageDraw

DEFAULT_SIZE = (1920, 1280)


def _exif_bytes(
    *,
    shot_at: str | None = None,
    make: bytes = b"Canon",
    model: bytes = b"EOS R6",
    serial: str | None = "CAM001",
) -> bytes:
    zeroth = {piexif.ImageIFD.Make: make, piexif.ImageIFD.Model: model}
    exif_ifd: dict[int, object] = {}
    if shot_at:
        exif_ifd[piexif.ExifIFD.DateTimeOriginal] = shot_at.encode()
    if serial:
        exif_ifd[piexif.ExifIFD.BodySerialNumber] = serial.encode()
    return piexif.dump({"0th": zeroth, "Exif": exif_ifd, "GPS": {}, "1st": {}, "thumbnail": None})


def make_valid_jpeg(
    *,
    shot_at: str = "2026:08:20 18:56:19",
    size: tuple[int, int] = DEFAULT_SIZE,
    color: tuple[int, int, int] = (90, 110, 130),
    serial: str | None = "CAM001",
) -> bytes:
    """JPEG valide, EXIF complet — le cas nominal."""
    img = Image.new("RGB", size, color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=_exif_bytes(shot_at=shot_at, serial=serial), quality=90)
    return buf.getvalue()


def make_no_exif_jpeg(size: tuple[int, int] = DEFAULT_SIZE) -> bytes:
    """JPEG valide, sans aucun EXIF — doit finir dans le bac « à rattacher »."""
    img = Image.new("RGB", size, (10, 10, 10))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def make_truncated_jpeg(**kwargs: object) -> bytes:
    """Fichier tronqué à 40 % — doit finir en quarantaine `truncated_file`."""
    data = make_valid_jpeg(**kwargs)  # type: ignore[arg-type]
    return data[: int(len(data) * 0.4)]


def make_undersized_jpeg() -> bytes:
    """Dimensions sous le plancher `[640..12000]` — quarantaine `dimensions_out_of_range`."""
    img = Image.new("RGB", (100, 100), (200, 50, 50))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def make_not_an_image() -> bytes:
    """Octets quelconques suffixés `.jpg` — quarantaine `not_an_image`."""
    return b"this is not a jpeg file at all, just plain text padding" * 20


def make_burst_frame(offset: int, *, shot_at: datetime.datetime, serial: str = "CAM001") -> bytes:
    """Une image d'une rafale : texture + sujet qui se déplace légèrement (§3-G.3).

    Un aplat de couleur unie défait le hash perceptuel (coefficients DCT quasi nuls,
    bruit flottant dominant) — la texture + le déplacement modéré reproduisent une vraie
    rafale de sport mécanique (constaté en conditions réelles lors de la vérification
    manuelle du pipeline).
    """
    img = Image.new("RGB", DEFAULT_SIZE, (90, 110, 130))
    draw = ImageDraw.Draw(img)
    for y in range(0, DEFAULT_SIZE[1], 40):
        draw.line([(0, y), (DEFAULT_SIZE[0], y)], fill=(70, 90, 110), width=8)
    x = 600 + offset * 20
    draw.ellipse([x, 500, x + 400, 900], fill=(200, 60, 40))
    buf = io.BytesIO()
    exif = _exif_bytes(shot_at=shot_at.strftime("%Y:%m:%d %H:%M:%S"), serial=serial)
    img.save(buf, format="JPEG", exif=exif, quality=92)
    return buf.getvalue()
