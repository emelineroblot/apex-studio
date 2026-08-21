"""`apex.pipeline.exif` — extraction tolérante, en particulier la sérialisation JSON de
`exif_raw` (§ régression trouvée en sourçant de vraies photos, `.agent-team/implementation.md`,
section Backend).
"""

from __future__ import annotations

import io
import json

import piexif
from PIL import Image

from apex.pipeline.exif import extract_exif


def _jpeg_with_embedded_nul_maker_note() -> bytes:
    """Reproduit un `MakerNote` (tag EXIF 37500) contenant des octets NUL **embarqués**,
    pas seulement en tête/queue — courant sur du matériel réel (constaté en sourçant des
    photos Wikimedia Commons), jamais produit par les fixtures EXIF fabriquées en test
    (`tests/support/images.py`, EXIF minimal et propre).
    """
    maker_note = b"OLYMPUS\x00\x04\x00\x01\x00\x00\x00binary\x00blob\x00trailing"
    exif_ifd = {
        piexif.ExifIFD.DateTimeOriginal: b"2024:05:12 10:30:00",
        piexif.ExifIFD.MakerNote: maker_note,
    }
    exif_bytes = piexif.dump({"0th": {}, "Exif": exif_ifd, "GPS": {}, "1st": {}, "thumbnail": None})
    img = Image.new("RGB", (800, 600), (80, 90, 100))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif_bytes, quality=85)
    return buf.getvalue()


class TestExifRawNeverContainsAnEmbeddedNulByte:
    """PostgreSQL ne peut stocker aucun `\\x00` dans un `text`/`jsonb` — un `MakerNote`
    binaire mal décodé faisait passer l'échec du filtrage en base au lieu d'une extraction
    tolérante (§ `_decode_str`, revue backend « sourcing des photos réelles »).
    """

    def test_maker_note_with_embedded_nul_bytes_is_sanitized(self) -> None:
        data = _jpeg_with_embedded_nul_maker_note()

        result = extract_exif(data)

        assert result.shot_at_exif is not None
        assert result.raw is not None
        serialized = json.dumps(result.raw)
        assert "\x00" not in serialized
        assert "\\u0000" not in serialized

    def test_maker_note_text_is_still_readable_around_the_stripped_bytes(self) -> None:
        data = _jpeg_with_embedded_nul_maker_note()

        result = extract_exif(data)

        assert result.raw is not None
        maker_note_value = result.raw["Exif"][str(piexif.ExifIFD.MakerNote)]
        assert "OLYMPUS" in maker_note_value
        assert "binary" in maker_note_value
        assert "blob" in maker_note_value
