"""Vignette et aperçu filigrané (§3-F.1 étape 5, §3-H.3) — WebP qualité 80, filigrane
**cuit dans les pixels** de l'aperçu (jamais un overlay CSS, contournable en un clic droit).
"""

from __future__ import annotations

import io
import unicodedata

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


#: Remplacements typographiques appliqués **avant** la réduction à l'ASCII : `unicodedata`
#: décompose « ç » en « c », mais supprimerait purement et simplement un tiret cadratin.
_TYPOGRAPHIC_FALLBACKS = {"—": "-", "–": "-", "’": "'", "«": '"', "»": '"', "…": "..."}


def _ascii_only(text: str) -> str:
    """Réduit le filigrane à l'ASCII imprimable.

    `_load_font` retombe sur la police par défaut de Pillow dès que `DejaVuSans-Bold.ttf`
    est introuvable — le cas sur Windows, et sur toute image Linux sans les polices
    système, donc potentiellement en production. Cette police ne couvre que l'ASCII :
    « Studio Chicane — aperçu » s'y dessine « Studio Chicane ▯ aper▯u ». Constaté en
    rendant un vrai aperçu, jamais visible en test (aucun test ne regarde les pixels du
    filigrane). Un filigrane sans accents vaut mieux qu'un filigrane à trous ; embarquer
    une police dans le dépôt et le paquet déployé coûterait plus que le gain esthétique
    sur une image volontairement dégradée.
    """
    for source, replacement in _TYPOGRAPHIC_FALLBACKS.items():
        text = text.replace(source, replacement)
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if 32 <= ord(c) < 127).strip() or "APERCU"


def apply_watermark(img: Image.Image, text: str) -> Image.Image:
    """Texte répété en diagonale, opacité 22 %, taille proportionnelle à la largeur (§3-H.3)."""
    text = _ascii_only(text)
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


def watermark_encoded_image(data: bytes, watermark_text: str) -> bytes:
    """Filigrane une image **déjà encodée** et la ré-encode en WebP.

    Sert la piste retenue en revue J1 pour J3 (voir `build_thumb`) : la vignette stockée
    reste propre — pHash et netteté sont calculés dessus et une texture répétée les
    fausserait — et le filigrane n'est appliqué qu'à la copie réellement transmise à un
    client externe. Fait à la volée plutôt que stocké : une variante de plus par média
    coûterait du stockage et une étape de pipeline pour une image qui n'est demandée que
    pendant les quelques jours de vie d'un lien de partage.

    Ne masque aucune erreur : une image illisible remonte l'exception de Pillow à
    l'appelant, à qui il revient de décider quoi répondre.
    """
    with Image.open(io.BytesIO(data)) as source:
        return _to_webp(apply_watermark(source, watermark_text))
