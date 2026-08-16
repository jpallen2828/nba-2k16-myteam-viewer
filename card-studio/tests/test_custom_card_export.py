from __future__ import annotations

import json
from pathlib import Path
import zipfile

from PIL import Image

from app.models.player_art_model import PlayerTransform
from app.models.card_assets_model import CardAssetSelection
from app.models.project_model import CardProject, TemplateReference
from app.player_data.schema import ATTRIBUTE_GROUPS, SIGNATURE_GROUPS, TENDENCY_GROUPS, default_player_data
from app.services.custom_card_service import CUSTOM_CARD_FORMAT, CustomCardService


def test_schema_contains_every_verified_attribute_and_tendency_in_order():
    data = default_player_data()
    expected_attributes = [name for _, fields in ATTRIBUTE_GROUPS for name in fields]
    expected_tendencies = [name for _, fields in TENDENCY_GROUPS for name in fields]
    assert list(data["attributes"]) == expected_attributes
    assert list(data["tendencies"]) == expected_tendencies
    assert len(expected_attributes) == 61
    assert len(expected_tendencies) == 84


def test_signature_editor_uses_complete_authoritative_grouped_choices():
    fields = [field for _, group in SIGNATURE_GROUPS for field in group]
    assert [group for group, _ in SIGNATURE_GROUPS] == [
        "Jump Shooting", "Layups & Dunks", "Post Game", "Ball Handling", "Misc",
    ]
    assert len(fields) == 45
    assert all(field["options"] for field in fields)
    assert next(field for field in fields if field["key"] == "shooting_form")["options"][0] == (0, "RELEASE_1")


def test_custom_card_package_contains_png_and_complete_manifest(tmp_path: Path):
    data = default_player_data()
    data["identity"].update({
        "name": "Test Player", "year": 2016, "overall": 91, "franchise": "Boston Celtics",
        "primary_position": "SG", "secondary_position": "PG", "height_feet": 6, "height_inches": 5,
        "face_id": 1234, "portrait_id": 5678, "jersey_number": "00",
        "source_card_id": 777, "source_card_slug": "test-player",
        "source_identity_ids": {
            "graphic_id": 1234, "portrait_ref_a": 5601, "portrait_ref_b": 5602,
            "portrait_ref_c": 5603, "picture_id": 5678,
        },
        "loyalty": 95, "play_type_1": 2, "injury_type_1": 3, "injury_duration_days_1": 4,
    })
    data["attributes"]["standing_layup"] = 92
    data["tendencies"]["shot"] = 88
    data["badges"]["gameplay"]["deadeye"] = 3
    data["badges"]["gameplay"]["chasedown_artist"] = 3
    project = CardProject(
        template=TemplateReference("gold", ""),
        player_source_path=None,
        player_transform=PlayerTransform(0, 0, 1, 0, False),
        player_data=data,
    )
    target = tmp_path / "test.2k16custom"
    CustomCardService.export(project, Image.new("RGBA", (325, 455), (1, 2, 3, 255)), target, (325, 455))
    with zipfile.ZipFile(target) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == CUSTOM_CARD_FORMAT
        assert archive.read("card.png").startswith(b"\x89PNG")
        card = manifest["card"]
        assert card["name"] == "Test Player"
        assert card["id"] > 0
        assert card["attributes"]["standing_layup"] == 92
        assert card["tendencies"]["shot"] == 88
        assert card["badges"]["deadeye"] == 3
        assert card["badges"]["chasedown_artist"] == 3
        assert card["customPlayerData"]["faceId"] == 1234
        assert card["customPlayerData"]["portraitId"] == 5678
        assert card["parentCardId"] == 777
        assert card["parentCardSlug"] == "test-player"
        assert card["customPlayerData"]["inheritedIdentityIds"]["portrait_ref_b"] == 5602
        assert card["jerseyNumber"] == "00"
        assert card["customPlayerData"]["jerseyNumber"] == "00"
        assert card["wingspanValue"] == 50
        assert card["customPlayerData"]["wingspanValue"] == 50
        assert "wingspanInches" not in card
        assert card["customPlayerData"]["loyalty"] == 95
        assert card["customPlayerData"]["playType1"] == 2
        assert card["customPlayerData"]["injuryDurationDays1"] == 4


def test_promotion_logo_controls_exported_theme_and_collection(tmp_path: Path):
    data = default_player_data()
    data["identity"].update({
        "name": "Giannis Antetokounmpo",
        "franchise": "Milwaukee Bucks",
        "theme": "Custom",
        "collection": "Custom Cards",
    })
    project = CardProject(
        template=TemplateReference("pink_diamond", ""),
        player_source_path=None,
        player_transform=PlayerTransform(0, 0, 1, 0, False),
        card_assets=CardAssetSelection(promotion_logo_id="playoffs"),
        player_data=data,
    )
    target = tmp_path / "playoffs.2k16custom"
    CustomCardService.export(project, Image.new("RGBA", (325, 455)), target, (325, 455))
    with zipfile.ZipFile(target) as archive:
        card = json.loads(archive.read("manifest.json"))["card"]
    assert card["promotionLogoId"] == "playoffs"
    assert card["theme"] == "Playoffs"
    assert card["collection"] == "Playoff Moments"


def test_promotion_logo_preserves_valid_specific_subcollection(tmp_path: Path):
    data = default_player_data()
    data["identity"].update({
        "name": "Giannis Antetokounmpo",
        "franchise": "Milwaukee Bucks",
        "theme": "Playoffs",
        "collection": "Playoff Moments: Finals",
    })
    project = CardProject(
        template=TemplateReference("pink_diamond", ""),
        player_source_path=None,
        player_transform=PlayerTransform(0, 0, 1, 0, False),
        card_assets=CardAssetSelection(promotion_logo_id="playoffs"),
        player_data=data,
    )
    target = tmp_path / "finals.2k16custom"
    CustomCardService.export(project, Image.new("RGBA", (325, 455)), target, (325, 455))
    with zipfile.ZipFile(target) as archive:
        card = json.loads(archive.read("manifest.json"))["card"]
    assert card["theme"] == "Playoffs"
    assert card["collection"] == "Playoff Moments: Finals"


def test_fiba_logo_exports_matching_theme_and_collection(tmp_path: Path):
    data = default_player_data()
    data["identity"].update({
        "name": "International Player",
        "franchise": "UNASSIGNED",
        "theme": "Custom",
        "collection": "Custom Cards",
    })
    project = CardProject(
        template=TemplateReference("diamond", ""),
        player_source_path=None,
        player_transform=PlayerTransform(0, 0, 1, 0, False),
        card_assets=CardAssetSelection(promotion_logo_id="fiba"),
        player_data=data,
    )
    target = tmp_path / "fiba.2k16custom"
    CustomCardService.export(project, Image.new("RGBA", (325, 455)), target, (325, 455))
    with zipfile.ZipFile(target) as archive:
        card = json.loads(archive.read("manifest.json"))["card"]
    assert card["promotionLogoId"] == "fiba"
    assert card["theme"] == "FIBA"
    assert card["collection"] == "FIBA"
