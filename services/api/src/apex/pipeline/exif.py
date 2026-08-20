"""Extraction EXIF tolérante (§3-F.1, étape 4) — chaque tag manquant devient `NULL`,
jamais une exception. Identification du boîtier et résolution du fuseau (§3-F.3) : le
rattachement horaire compare des **instants** (`shot_at`, `timestamptz`), jamais des
textes — `shot_at_exif` (naïf, tel que lu) reste distinct.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import piexif
from sqlalchemy import select
from sqlalchemy.orm import Session

from apex.models.catalog import Camera

_RationalT = tuple[int, int]


@dataclass(slots=True)
class ExifData:
    shot_at_exif: datetime | None = None
    camera_make: str | None = None
    camera_model: str | None = None
    camera_serial: str | None = None
    lens_model: str | None = None
    iso: int | None = None
    shutter_speed_sec: float | None = None
    shutter_speed_label: str | None = None
    aperture: float | None = None
    focal_length: float | None = None
    gps_lat: float | None = None
    gps_lon: float | None = None
    raw: dict[str, Any] | None = None


def _decode_str(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace").strip("\x00").strip() or None
        except Exception:  # noqa: BLE001 — extraction tolérante, jamais d'exception remontée
            return None
    text = str(value).strip()
    return text or None


def _rational_to_float(value: Any) -> float | None:
    try:
        num, den = value
        if den == 0:
            return None
        return float(num) / float(den)
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _shutter_label(seconds: float | None) -> str | None:
    if seconds is None or seconds <= 0:
        return None
    if seconds >= 1:
        return f"{seconds:.1f}s"
    denominator = round(1 / seconds)
    return f"1/{denominator}"


def _dms_to_decimal(dms: Any, ref: Any) -> float | None:
    try:
        degrees = _rational_to_float(dms[0])
        minutes = _rational_to_float(dms[1])
        seconds = _rational_to_float(dms[2])
        if degrees is None or minutes is None or seconds is None:
            return None
        decimal = degrees + minutes / 60.0 + seconds / 3600.0
    except (TypeError, IndexError):
        return None
    ref_str = _decode_str(ref)
    if ref_str in ("S", "W"):
        decimal = -decimal
    return decimal


def _parse_datetime(raw: Any) -> datetime | None:
    text = _decode_str(raw)
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y:%m:%d %H:%M:%S")
    except ValueError:
        return None


def extract_exif(data: bytes) -> ExifData:
    """Ne lève jamais — un flux non-JPEG ou sans EXIF renvoie un `ExifData` vide."""
    try:
        exif_dict = piexif.load(data)
    except Exception:  # noqa: BLE001 — extraction tolérante (§3-F.1)
        return ExifData()

    zeroth = exif_dict.get("0th", {}) or {}
    exif_ifd = exif_dict.get("Exif", {}) or {}
    gps_ifd = exif_dict.get("GPS", {}) or {}

    shutter_sec = _rational_to_float(exif_ifd.get(piexif.ExifIFD.ExposureTime))
    result = ExifData(
        shot_at_exif=_parse_datetime(exif_ifd.get(piexif.ExifIFD.DateTimeOriginal)),
        camera_make=_decode_str(zeroth.get(piexif.ImageIFD.Make)),
        camera_model=_decode_str(zeroth.get(piexif.ImageIFD.Model)),
        camera_serial=_decode_str(exif_ifd.get(piexif.ExifIFD.BodySerialNumber)),
        lens_model=_decode_str(exif_ifd.get(piexif.ExifIFD.LensModel)),
        iso=_safe_int(exif_ifd.get(piexif.ExifIFD.ISOSpeedRatings)),
        shutter_speed_sec=shutter_sec,
        shutter_speed_label=_shutter_label(shutter_sec),
        aperture=_rational_to_float(exif_ifd.get(piexif.ExifIFD.FNumber)),
        focal_length=_rational_to_float(exif_ifd.get(piexif.ExifIFD.FocalLength)),
        gps_lat=_dms_to_decimal(
            gps_ifd.get(piexif.GPSIFD.GPSLatitude), gps_ifd.get(piexif.GPSIFD.GPSLatitudeRef)
        ),
        gps_lon=_dms_to_decimal(
            gps_ifd.get(piexif.GPSIFD.GPSLongitude), gps_ifd.get(piexif.GPSIFD.GPSLongitudeRef)
        ),
        raw=_json_safe_raw(exif_dict),
    )
    return result


def _safe_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        if isinstance(value, list | tuple) and value:
            value = value[0]
        return int(value)
    except (TypeError, ValueError):
        return None


def _json_safe_raw(exif_dict: dict[str, Any]) -> dict[str, Any]:
    """Version JSON-sérialisable de l'EXIF brut — stockée dans `media.exif_raw` (JSONB)."""

    def _convert(value: Any) -> Any:
        if isinstance(value, bytes):
            return _decode_str(value)
        if isinstance(value, tuple):
            return [_convert(v) for v in value]
        if isinstance(value, list):
            return [_convert(v) for v in value]
        if isinstance(value, dict):
            return {str(k): _convert(v) for k, v in value.items()}
        return value

    return {
        section: _convert(values)
        for section, values in exif_dict.items()
        if section != "thumbnail" and isinstance(values, dict)
    }


def resolve_camera(session: Session, exif: ExifData) -> Camera | None:
    """Identification du boîtier (§3-F.3) : n° de série, repli sur `make|model` (catalog.py).

    Crée le boîtier s'il est inconnu — c'est le comportement attendu : un boîtier
    « apparaît » au premier média qui en porte la trace, avec un décalage d'horloge nul
    par défaut, réglable ensuite via `PATCH /cameras/{id}`.
    """
    if exif.camera_serial:
        camera = session.execute(
            select(Camera).where(Camera.exif_serial == exif.camera_serial)
        ).scalar_one_or_none()
        if camera is not None:
            return camera
        camera = Camera(
            exif_serial=exif.camera_serial, make=exif.camera_make, model=exif.camera_model
        )
        session.add(camera)
        session.flush()
        return camera

    if exif.camera_make or exif.camera_model:
        camera = session.execute(
            select(Camera).where(
                Camera.exif_serial.is_(None),
                Camera.make == exif.camera_make,
                Camera.model == exif.camera_model,
            )
        ).scalar_one_or_none()
        if camera is not None:
            return camera
        camera = Camera(exif_serial=None, make=exif.camera_make, model=exif.camera_model)
        session.add(camera)
        session.flush()
        return camera

    return None


def compute_shot_at(shot_at_exif: datetime | None, camera: Camera | None) -> datetime | None:
    """`shot_at = localize(shot_at_exif, camera.timezone) + camera.clock_offset_seconds` (§3-F.3)."""
    if shot_at_exif is None:
        return None
    tz_name = camera.timezone if camera is not None else "Europe/Paris"
    try:
        tz = ZoneInfo(tz_name)
    except (ZoneInfoNotFoundError, ValueError):
        # Revue J1 (🔴 n°1, scénario reproduit) : `ZoneInfo("")` lève `ValueError`, pas
        # `ZoneInfoNotFoundError` — un fuseau vide ou mal formé (ex. bug côté validation
        # amont) ne doit jamais faire planter le pipeline. Défense en profondeur : la
        # valeur est désormais aussi validée à l'écriture (`schemas/catalog.CameraPatch`),
        # mais cette fonction reste tolérante par elle-même.
        tz = ZoneInfo("Europe/Paris")
    localized = shot_at_exif.replace(tzinfo=tz)
    offset = camera.clock_offset_seconds if camera is not None else 0
    return localized + timedelta(seconds=offset)
