"""`scripts/source_demo_photos.py` — logique pure (aucun appel réseau), § brief « sourcing
des photos réelles ». Le reste du script (téléchargement, pagination Commons) n'est pas
couvert ici : il dépend d'un service externe et se vérifie par exécution réelle
(§ `.agent-team/implementation.md`, section « vérification de bout en bout »), pas par la
suite `pytest` par défaut.
"""

from __future__ import annotations

from pathlib import Path

from scripts.source_demo_photos import (
    Manifest,
    dimensions_plausible,
    evaluate_candidate,
    first_href,
    is_people_heavy,
    license_is_free_enough,
    local_filename,
    slugify,
    strip_html,
    write_attributions_doc,
)


class TestLicenseFiltering:
    def test_cc0_is_accepted(self) -> None:
        assert license_is_free_enough("cc0-1.0") is True

    def test_public_domain_is_accepted(self) -> None:
        assert license_is_free_enough("pd-old-70") is True

    def test_cc_by_is_accepted(self) -> None:
        assert license_is_free_enough("cc-by-4.0") is True

    def test_cc_by_sa_is_accepted(self) -> None:
        assert license_is_free_enough("cc-by-sa-4.0") is True

    def test_non_commercial_is_rejected(self) -> None:
        assert license_is_free_enough("cc-by-nc-4.0") is False

    def test_no_derivatives_is_rejected(self) -> None:
        assert license_is_free_enough("cc-by-nd-4.0") is False

    def test_all_rights_reserved_is_rejected(self) -> None:
        assert license_is_free_enough("copyrighted") is False

    def test_missing_license_is_rejected(self) -> None:
        assert license_is_free_enough(None) is False


class TestPeopleHeavyHeuristic:
    def test_podium_shot_is_flagged(self) -> None:
        assert is_people_heavy("2023 Podium celebration", None, None, None) is True

    def test_portrait_is_flagged(self) -> None:
        assert is_people_heavy(None, "Driver portrait before the race", None, None) is True

    def test_plain_car_shot_is_not_flagged(self) -> None:
        assert is_people_heavy("Formula One car #44 at Silverstone", None, None, None) is False

    def test_matches_across_all_fields(self) -> None:
        assert is_people_heavy("Car #12", None, None, "Grid girls|Formula One cars") is True


class TestDimensionsPlausible:
    def test_typical_dslr_photo_is_plausible(self) -> None:
        assert dimensions_plausible(4000, 3000) is True

    def test_too_small_is_rejected(self) -> None:
        assert dimensions_plausible(200, 150) is False

    def test_extreme_aspect_ratio_is_rejected(self) -> None:
        assert dimensions_plausible(6000, 400) is False

    def test_zero_height_never_raises(self) -> None:
        assert dimensions_plausible(4000, 0) is False


class TestHtmlAndSlugHelpers:
    def test_strip_html_removes_tags_and_decodes_entities(self) -> None:
        raw = '<a href="//commons.wikimedia.org/wiki/User:Bearas">Bearas &amp; co</a>'
        assert strip_html(raw) == "Bearas & co"

    def test_first_href_extracts_and_normalizes_protocol_relative_url(self) -> None:
        raw = '<a href="//commons.wikimedia.org/wiki/User:Bearas">Bearas</a>'
        assert first_href(raw) == "https://commons.wikimedia.org/wiki/User:Bearas"

    def test_first_href_returns_none_without_a_link(self) -> None:
        assert first_href("<span>Own work</span>") is None

    def test_slugify_strips_extension_and_punctuation(self) -> None:
        assert slugify("File:20260704 131105 Formula1 in Cardiff.jpg") == (
            "20260704-131105-formula1-in-cardiff"
        )

    def test_local_filename_is_zero_padded_and_sorts_numerically(self) -> None:
        assert local_filename(7, "File:Some Car.jpg") == "0007_some-car.jpg"


class TestEvaluateCandidateMetadataOnly:
    def _page(self, **overrides: object) -> dict[str, object]:
        base: dict[str, object] = {
            "title": "File:Example F1 car.jpg",
            "imageinfo": [
                {
                    "mime": "image/jpeg",
                    "width": 4000,
                    "height": 3000,
                    "size": 3_000_000,
                    "url": "https://upload.wikimedia.org/example.jpg",
                    "descriptionurl": "https://commons.wikimedia.org/wiki/File:Example.jpg",
                    "extmetadata": {
                        "License": {"value": "cc-by-sa-4.0"},
                        "LicenseShortName": {"value": "CC BY-SA 4.0"},
                        "LicenseUrl": {"value": "https://creativecommons.org/licenses/by-sa/4.0"},
                        "Artist": {"value": '<a href="//x/User:A">A</a>'},
                        "Credit": {"value": "<span>Own work</span>"},
                    },
                }
            ],
        }
        base.update(overrides)
        return base

    def test_a_clean_free_license_car_photo_is_accepted(self) -> None:
        info, reason = evaluate_candidate("Formula One cars", self._page())
        assert reason is None
        assert info is not None
        assert info["license_code"] == "cc-by-sa-4.0"

    def test_wrong_mime_is_rejected(self) -> None:
        page = self._page()
        page["imageinfo"][0]["mime"] = "image/png"  # type: ignore[index]
        info, reason = evaluate_candidate("Formula One cars", page)
        assert info is None
        assert reason is not None and reason.startswith("unsupported_mime")

    def test_non_free_license_is_rejected(self) -> None:
        page = self._page()
        page["imageinfo"][0]["extmetadata"]["License"] = {"value": "cc-by-nc-4.0"}  # type: ignore[index]
        info, reason = evaluate_candidate("Formula One cars", page)
        assert info is None
        assert reason is not None and reason.startswith("license_not_free")

    def test_people_heavy_title_is_rejected(self) -> None:
        page = self._page(title="File:Podium celebration 2023.jpg")
        info, reason = evaluate_candidate("Formula One cars", page)
        assert info is None
        assert reason == "people_heavy_framing"

    def test_missing_imageinfo_is_rejected(self) -> None:
        info, reason = evaluate_candidate("Formula One cars", {"title": "File:X.jpg"})
        assert info is None
        assert reason == "no_imageinfo"


class TestManifestRoundtrip:
    def test_save_then_load_preserves_entries(self, tmp_path: Path) -> None:
        manifest = Manifest(path=tmp_path / ".sourcing-manifest.json")
        manifest.entries["123"] = {"status": "accepted", "filename": "0001_x.jpg"}
        manifest.save()

        reloaded = Manifest.load(tmp_path / ".sourcing-manifest.json")
        assert reloaded.entries == manifest.entries

    def test_load_on_missing_file_returns_empty_manifest(self, tmp_path: Path) -> None:
        manifest = Manifest.load(tmp_path / "absent.json")
        assert manifest.entries == {}

    def test_accepted_count_on_disk_ignores_entries_without_a_file(self, tmp_path: Path) -> None:
        (tmp_path / "0001_x.jpg").write_bytes(b"fake")
        manifest = Manifest(path=tmp_path / ".sourcing-manifest.json")
        manifest.entries["1"] = {"status": "accepted", "filename": "0001_x.jpg"}
        manifest.entries["2"] = {"status": "accepted", "filename": "0002_missing.jpg"}
        manifest.entries["3"] = {"status": "rejected", "reason": "license_not_free"}

        assert manifest.accepted_count_on_disk(tmp_path) == 1


class TestAttributionsDoc:
    def test_writes_a_markdown_table_with_the_image_rights_caveat(self, tmp_path: Path) -> None:
        manifest = Manifest(path=tmp_path / ".sourcing-manifest.json")
        manifest.entries["1"] = {
            "status": "accepted",
            "filename": "0001_car.jpg",
            "title": "File:Car.jpg",
            "author": "Jane Doe",
            "license_short": "CC BY-SA 4.0",
            "license_code": "cc-by-sa-4.0",
            "source_url": "https://commons.wikimedia.org/wiki/File:Car.jpg",
            "category": "Formula One cars",
            "exif": {"camera_model": "EOS R6"},
        }
        doc_path = tmp_path / "attributions.md"

        count = write_attributions_doc(manifest, doc_path=doc_path, out_dir=tmp_path)

        assert count == 1
        content = doc_path.read_text(encoding="utf-8")
        assert "0001_car.jpg" in content
        assert "Jane Doe" in content
        assert "CC BY-SA 4.0" in content
        assert "droit à l'image" in content.lower()
        assert "ne couvrent" in content.lower()
