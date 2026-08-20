"""Vignette et aperçu filigrané (§3-F.1 étape 5, §3-H.3) — WebP qualité 80, filigrane
**cuit dans les pixels** de l'aperçu (jamais un overlay CSS, contournable en un clic droit).
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont, ImageOps

THUMB_MAX_SIDE = 320
PREVIEW_MAX_SIDE = 1600
WEBP_QUALITY = 80
WATERMARK_OPACITY = 0.22
WATERMARK_ROTATION_DEG = -30


def _resize_max_side(img: Image.Image, max_side: int) -> Image.Image:
    width, height = img.size
    longest = max(width, height)
    if longest <= max_side:
        return img.copy()
    scale = max_side / longest
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    return img.resize(new_size, Image.Resampling.LANCZOS)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except OSError:
        return ImageFont.load_default()


def apply_watermark(img: Image.Image, text: str) -> Image.Image:
    """Texte répété en diagonale, opacité 22 %, taille proportionnelle à la largeur (§3-H.3)."""
    base = img.convert("RGBA")
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = max(16, base.width // 16)
    font = _load_font(font_size)
    alpha = int(255 * WATERMARK_OPACITY)
    step_x = font_size * 8
    step_y = font_size * 5

    for y in range(-base.height, base.height * 2, step_y):
        for x in range(-base.width, base.width * 2, step_x):
            draw.text((x, y), text, font=font, fill=(255, 255, 255, alpha))

    rotated = overlay.rotate(WATERMARK_ROTATION_DEG, resample=Image.Resampling.BICUBIC)
    # Recadre au centre à la taille d'origine (`rotate(expand=False)` garde déjà la taille).
    watermarked = Image.alpha_composite(base, rotated)
    return watermarked.convert("RGB")


def _to_webp(img: Image.Image, *, quality: int = WEBP_QUALITY) -> bytes:
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="WEBP", quality=quality)
    return buf.getvalue()


def build_thumb(img: Image.Image) -> bytes:
    """Vignette 320 px — **volontairement non filigranée** (revue J1, point d'attention
    signalé, non corrigé à l'aveugle).

    `pipeline/ingest.py` calcule le pHash (§3-G.2) et la netteté (§3-G.3) directement sur
    cette vignette : un filigrane cuit dans les pixels y introduirait une texture répétée
    qui fausserait la DCT basses fréquences (pHash) et la variance de Laplacien
    (netteté) — deux doublons légitimement identiques pourraient diverger, et le choix du
    représentant le plus net serait biaisé par la densité du filigrane plutôt que par le
    contenu réel de la photo.

    §3-H.2 exige que thumb *et* preview soient filigranés une fois servis au client — ce
    qui reste vrai pour `preview` (`build_watermarked_preview`, ci-dessous). Pour `thumb`,
    l'écart est assumé pour J1 : elle sert aujourd'hui en interne uniquement (grille photo
    des rôles `owner`/`photographer`, jamais exposée à un client externe avant J3). Piste
    retenue pour J3, quand `thumb` sera servie au client (`GET /media/{id}/file/thumb`
    accessible à la portée « client ») : calculer pHash/netteté sur la vignette **avant**
    filigrane (ordre déjà respecté ici : cette fonction ne filigrane jamais), puis
    appliquer un filigrane séparé uniquement sur la variante réellement transmise à un
    client — sans jamais réutiliser cette même vignette qui, elle, doit rester propre pour
    le calcul.
    """
    oriented = ImageOps.exif_transpose(img) or img
    thumb = _resize_max_side(oriented.convert("RGB"), THUMB_MAX_SIDE)
    return _to_webp(thumb)


def build_watermarked_preview(img: Image.Image, watermark_text: str) -> bytes:
    oriented = ImageOps.exif_transpose(img) or img
    preview = _resize_max_side(oriented.convert("RGB"), PREVIEW_MAX_SIDE)
    watermarked = apply_watermark(preview, watermark_text)
    return _to_webp(watermarked)
