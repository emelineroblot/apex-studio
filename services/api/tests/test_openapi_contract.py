"""Verrouille la cohérence des énumérations exposées au contrat OpenAPI (`apex.schemas.media`)
avec leur source de vérité modèle (`apex.models.media`).

Contexte (revue d'intégration live J1) : trois fois de suite, le backend a émis une clé de
motif (quarantaine, non-rattachement) que le frontend ne savait pas traduire — `quarantine_reason`
et le contenu de `attachment_detail` étaient exposés en `str`/`dict` libres dans l'OpenAPI, alors
que ce sont des ensembles fermés côté modèle. Le frontend avait dû recopier la liste à la main,
d'où des clés manquantes (motif ajouté ici, jamais reporté là-bas) et des clés fantômes (motif
renommé/supprimé ici, oublié là-bas — cas de `exif_inconsistent`, qui n'était plus jamais produit
avant son correctif).

Ce test ne remplace pas les tests fonctionnels par motif (`tests/pipeline/test_quarantine_and_listing.py`
et consorts, qui prouvent que chaque valeur est réellement produite) : il verrouille que le type
exposé au contrat (`Literal` Pydantic → énumération OpenAPI → union TypeScript fermée après
`npm run gen:api`) ne diverge jamais, dans un sens comme dans l'autre, du tuple qui sert de source
de vérité pour le `CHECK` en base (`quarantine_reason`) ou pour les motifs écrits par le pipeline
de rattachement (`attachment_detail.reason`).
"""

from __future__ import annotations

from typing import get_args

from apex.models.media import QUARANTINE_DETAIL_KEYS, QUARANTINE_REASONS, UNATTACHED_REASONS
from apex.models.search import OCR_RESOLUTIONS
from apex.schemas.media import AttachmentUnattachedReason, QuarantineDetail, QuarantineReason
from apex.schemas.review import OcrResolution


def test_quarantine_reason_enum_matches_model() -> None:
    """`QuarantineReason` (contrat OpenAPI) doit lister exactement les mêmes valeurs que
    `QUARANTINE_REASONS` (source de vérité, `CHECK quarantine_reason_valid`) — ni motif
    manquant (le frontend ne pourrait pas le traduire), ni motif fantôme (le frontend
    traduirait un code que le backend n'émet plus jamais).
    """
    exposed = set(get_args(QuarantineReason))
    modeled = set(QUARANTINE_REASONS)
    assert exposed == modeled, (
        f"divergence contrat OpenAPI ↔ modèle sur quarantine_reason — "
        f"manquants au contrat : {modeled - exposed} ; fantômes au contrat : {exposed - modeled}"
    )


def test_attachment_unattached_reason_enum_matches_model() -> None:
    """`AttachmentUnattachedReason` (contrat OpenAPI, champ `AttachmentDetail.reason`) doit
    lister exactement les mêmes valeurs que `UNATTACHED_REASONS` (source de vérité, motifs
    écrits par `apex/pipeline/attach_time.py`).
    """
    exposed = set(get_args(AttachmentUnattachedReason))
    modeled = set(UNATTACHED_REASONS)
    assert exposed == modeled, (
        f"divergence contrat OpenAPI ↔ modèle sur attachment_detail.reason — "
        f"manquants au contrat : {modeled - exposed} ; fantômes au contrat : {exposed - modeled}"
    )


def test_ocr_resolution_enum_matches_model() -> None:
    """`OcrResolution` (contrat OpenAPI, `ReviewItem.resolution` / `OcrCandidateOut.resolution`)
    doit lister exactement les mêmes valeurs que `OCR_RESOLUTIONS` (source de vérité, `CHECK
    resolution_valid` sur `media_ocr_candidate`) — sans quoi la distinction « pas sûr »
    (`review`) / « sûr mais incohérent » (`not_engaged`) redeviendrait une déduction fragile
    côté frontend plutôt qu'une énumération fermée (cf. docstring de `apex.schemas.review`).
    """
    exposed = set(get_args(OcrResolution))
    modeled = set(OCR_RESOLUTIONS)
    assert exposed == modeled, (
        f"divergence contrat OpenAPI ↔ modèle sur resolution — "
        f"manquants au contrat : {modeled - exposed} ; fantômes au contrat : {exposed - modeled}"
    )


def test_quarantine_detail_keys_match_model() -> None:
    """`QuarantineDetail` (contrat OpenAPI) doit déclarer exactement les mêmes clés que
    `QUARANTINE_DETAIL_KEYS` (source de vérité — vocabulaire fermé des clés effectivement
    écrites par le pipeline dans `quarantine_detail`, cf. `apex/pipeline/integrity.py`,
    `apex/pipeline/ingest.py`, `apex/queue/handlers/ingest_media.py`,
    `apex/queue/handlers/sweep_orphans.py`, `apex/routers/batches.py`).
    """
    exposed = set(QuarantineDetail.model_fields)
    modeled = set(QUARANTINE_DETAIL_KEYS)
    assert exposed == modeled, (
        f"divergence contrat OpenAPI ↔ modèle sur quarantine_detail — "
        f"manquantes au contrat : {modeled - exposed} ; fantômes au contrat : {exposed - modeled}"
    )
