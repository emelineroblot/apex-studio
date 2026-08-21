"""Tests **déterministes** de la couche Exécution : normalisation, géométrie, score, décision.

Aucun modèle, aucune base : ces fonctions sont pures, et c'est tout l'intérêt du découpage
DOE. Ce qui est testé ici est exactement ce qui tourne en production — `classify.decide` est
la fonction utilisée par le handler, par le routeur de réglages et par l'évaluation offline.
"""

from __future__ import annotations

import pytest

from apex.pipeline.ocr import classify
from apex.pipeline.ocr.engine import TextBox
from apex.pipeline.ocr.normalize import canonical_number, normalize_text
from apex.pipeline.ocr.scoring import (
    PURITY_FLOOR,
    SINGLE_DIGIT_PENALTY,
    compute_geometry,
    compute_score,
    extract_readings,
    passes_geometry_filter,
)
from apex.services.ocr_settings import OCR_HIGH_DEFAULT

IMAGE_W, IMAGE_H = 1600, 1067
DEFAULTS = {
    "min_box_area_ratio": 0.0005,
    "max_box_area_ratio": 0.08,
    "top_margin_ratio": 0.10,
}


def _quad(x0: float, y0: float, width: float, height: float):
    return ((x0, y0), (x0 + width, y0), (x0 + width, y0 + height), (x0, y0 + height))


class TestNormalisation:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("12", "12"),
            (" 42 ", "42"),
            ("N°7", "7"),
            ("#250", "250"),
            ("O7", "07"),  # confusion O→0
            ("I2", "12"),  # confusion I→1
            ("B", "8"),  # une seule lettre, mais un chiffre plausible
            ("S0", "50"),  # confusion S→5 : plausible, mais peu pur (cf. score)
        ],
    )
    def test_reads_a_car_number(self, raw: str, expected: str) -> None:
        assert normalize_text(raw).number == expected

    @pytest.mark.parametrize(
        "raw",
        [
            "",
            "   ",
            "PIRELLI",  # ne laisse que des 1 issus des I/L → 4 chiffres, hors format
            "1234",  # 4 chiffres : au-delà d'un numéro de course
            "@@@",
        ],
    )
    def test_rejects_what_is_not_a_car_number(self, raw: str) -> None:
        assert normalize_text(raw).number is None

    def test_a_sponsor_name_can_survive_the_format_check_and_that_is_expected(self) -> None:
        """« MICHELIN » devient « 111 » : format valide, et pourtant ce n'est pas un numéro.

        Constat fait en écrivant ce test — la regex `^[0-9]{1,3}$` ne suffit **pas** à
        écarter un lettrage de sponsor, puisque les confusions typographiques peuvent
        fabriquer un numéro plausible de toutes pièces. C'est exactement ce que le facteur
        de pureté existe pour rattraper : la lecture est conservée (on ne jette rien en
        silence) mais son score s'effondre, donc elle ne peut pas rattacher toute seule.
        Sans ce garde-fou, un flanc de pneu livrerait des photos au n°111.
        """
        normalized = normalize_text("MICHELIN")
        assert normalized.number == "111"
        assert normalized.digit_purity == 0.0

        geometry = compute_geometry(_quad(700, 500, 200, 220), IMAGE_W, IMAGE_H)
        breakdown = compute_score(
            model_confidence=0.99,
            geometry=geometry,
            normalized=normalized,
            min_box_area_ratio=DEFAULTS["min_box_area_ratio"],
        )
        assert breakdown.score < OCR_HIGH_DEFAULT

    def test_tracks_purity_to_penalise_reconstructed_readings(self) -> None:
        """« SO » ne devient « 50 » qu'à coups de substitutions : le score doit s'en souvenir."""
        pure = normalize_text("50")
        reconstructed = normalize_text("SO")
        assert pure.number == reconstructed.number == "50"
        assert pure.digit_purity == 1.0
        assert reconstructed.digit_purity == 0.0
        assert reconstructed.substitutions == 2

    @pytest.mark.parametrize(
        ("value", "expected"), [("07", "7"), ("7", "7"), ("007", "7"), ("250", "250"), ("7B", "7B")]
    )
    def test_canonical_form_bridges_writing_conventions(self, value: str, expected: str) -> None:
        """« 07 » lu et « 7 » saisi à la table des engagements doivent se rencontrer."""
        assert canonical_number(value) == expected


class TestFiltrageGeometrique:
    def test_accepts_a_plausible_number_plate(self) -> None:
        geometry = compute_geometry(_quad(700, 500, 160, 190), IMAGE_W, IMAGE_H)
        assert passes_geometry_filter(geometry, **DEFAULTS)

    def test_rejects_a_box_too_small_to_be_a_number(self) -> None:
        geometry = compute_geometry(_quad(700, 500, 8, 8), IMAGE_W, IMAGE_H)
        assert not passes_geometry_filter(geometry, **DEFAULTS)

    def test_rejects_a_box_covering_a_billboard(self) -> None:
        geometry = compute_geometry(_quad(100, 300, 1200, 700), IMAGE_W, IMAGE_H)
        assert not passes_geometry_filter(geometry, **DEFAULTS)

    def test_rejects_the_sky(self) -> None:
        """Le ciel ne porte pas de numéro de course — bande haute écartée par construction."""
        geometry = compute_geometry(_quad(700, 5, 160, 60), IMAGE_W, IMAGE_H)
        assert not passes_geometry_filter(geometry, **DEFAULTS)

    def test_rejects_a_degenerate_ribbon(self) -> None:
        geometry = compute_geometry(_quad(200, 600, 900, 20), IMAGE_W, IMAGE_H)
        assert not passes_geometry_filter(geometry, **DEFAULTS)


class TestScore:
    def test_a_clean_reading_keeps_its_confidence(self) -> None:
        geometry = compute_geometry(_quad(700, 500, 200, 220), IMAGE_W, IMAGE_H)
        breakdown = compute_score(
            model_confidence=0.99,
            geometry=geometry,
            normalized=normalize_text("12"),
            min_box_area_ratio=DEFAULTS["min_box_area_ratio"],
        )
        assert breakdown.geometry_factor == pytest.approx(1.0)
        assert breakdown.length_factor == 1.0
        assert breakdown.purity_factor == 1.0
        assert breakdown.score == pytest.approx(0.99)

    def test_a_single_digit_is_penalised(self) -> None:
        geometry = compute_geometry(_quad(700, 500, 200, 220), IMAGE_W, IMAGE_H)
        breakdown = compute_score(
            model_confidence=0.99,
            geometry=geometry,
            normalized=normalize_text("7"),
            min_box_area_ratio=DEFAULTS["min_box_area_ratio"],
        )
        assert breakdown.length_factor == SINGLE_DIGIT_PENALTY
        assert breakdown.score < 0.99

    def test_a_reconstructed_reading_cannot_reach_the_high_band_alone(self) -> None:
        """Le garde-fou anti-faux-positif : « SO » lu à 0,99 ne doit pas rattacher le n°50."""
        geometry = compute_geometry(_quad(700, 500, 200, 220), IMAGE_W, IMAGE_H)
        breakdown = compute_score(
            model_confidence=0.99,
            geometry=geometry,
            normalized=normalize_text("SO"),
            min_box_area_ratio=DEFAULTS["min_box_area_ratio"],
        )
        assert breakdown.purity_factor == PURITY_FLOOR
        assert breakdown.score < OCR_HIGH_DEFAULT, "resterait sous le seuil de rattachement auto"

    def test_score_stays_within_bounds(self) -> None:
        geometry = compute_geometry(_quad(700, 500, 200, 220), IMAGE_W, IMAGE_H)
        breakdown = compute_score(
            model_confidence=1.5,  # un moteur qui déborderait ne doit pas casser l'échelle
            geometry=geometry,
            normalized=normalize_text("12"),
            min_box_area_ratio=DEFAULTS["min_box_area_ratio"],
        )
        assert 0.0 <= breakdown.score <= 1.0


class TestExtractionDesLectures:
    def test_two_distinct_numbers_produce_two_readings(self) -> None:
        """Deux voitures numérotées dans le cadre : deux candidats, donc deux rattachements."""
        boxes = [
            TextBox("12", 0.97, _quad(400, 500, 180, 200)),
            TextBox("250", 0.93, _quad(1000, 520, 220, 200)),
        ]
        readings = extract_readings(boxes, image_width=IMAGE_W, image_height=IMAGE_H, **DEFAULTS)
        assert [reading.normalized_number for reading in readings] == ["12", "250"]

    def test_the_same_number_read_twice_is_deduplicated(self) -> None:
        """Deux fois le n°12 dans le cadre, c'est une voiture vue deux fois."""
        boxes = [
            TextBox("12", 0.70, _quad(400, 500, 180, 200)),
            TextBox("12", 0.95, _quad(1000, 520, 180, 200)),
        ]
        readings = extract_readings(boxes, image_width=IMAGE_W, image_height=IMAGE_H, **DEFAULTS)
        assert len(readings) == 1
        assert readings[0].score == pytest.approx(0.95)

    def test_sponsor_lettering_is_dropped_before_scoring(self) -> None:
        boxes = [TextBox("PIRELLI", 0.99, _quad(400, 700, 300, 60))]
        readings = extract_readings(boxes, image_width=IMAGE_W, image_height=IMAGE_H, **DEFAULTS)
        assert readings == []

    def test_bbox_is_normalised_for_the_ui_overlay(self) -> None:
        boxes = [TextBox("12", 0.9, _quad(400, 500, 160, 200))]
        [reading] = extract_readings(boxes, image_width=IMAGE_W, image_height=IMAGE_H, **DEFAULTS)
        assert reading.bbox["x"] == pytest.approx(400 / IMAGE_W, abs=1e-4)
        assert reading.bbox["w"] == pytest.approx(160 / IMAGE_W, abs=1e-4)
        assert reading.bbox["image_width"] == IMAGE_W
        assert len(reading.bbox["quad"]) == 4


class TestRegleDeDecision:
    """`classify.decide` — la règle complète, en quatre issues."""

    def test_above_high_attaches(self) -> None:
        assert classify.decide(matched=True, score=0.91, high=0.8, low=0.45) == "auto"

    def test_between_thresholds_goes_to_human_review(self) -> None:
        assert classify.decide(matched=True, score=0.60, high=0.8, low=0.45) == "review"

    def test_below_low_abstains(self) -> None:
        assert classify.decide(matched=True, score=0.20, high=0.8, low=0.45) == "abstain"

    @pytest.mark.parametrize("score", [0.99, 0.60, 0.05])
    def test_a_number_absent_from_the_entry_list_is_never_attached(self, score: float) -> None:
        """« Sûr mais incohérent » n'est pas « pas sûr » : issue distincte, quel que soit le score."""
        assert classify.decide(matched=False, score=score, high=0.8, low=0.45) == "not_engaged"

    def test_thresholds_are_inclusive_on_the_lower_bound(self) -> None:
        assert classify.decide(matched=True, score=0.80, high=0.8, low=0.45) == "auto"
        assert classify.decide(matched=True, score=0.45, high=0.8, low=0.45) == "review"
