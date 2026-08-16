from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from app.application import CardStudioApplication
from app.constants import BUILT_IN_TEMPLATE_ORDER
from app.models.player_art_model import PlayerTransform
from app.models.project_model import CardProject, TemplateReference, TextPlaceholders
from app.rendering.card_renderer import CardRenderer
from app.rendering.image_loader import load_player_image
from app.services.project_service import ProjectService
from app.services.template_service import TemplateService
from app.utilities.paths import AppPaths


ROOT = Path(__file__).resolve().parents[1]
BUILT_INS = ROOT / "assets" / "built_in_templates"
TEXT_STYLES = ROOT / "assets" / "text_styles"
LEGACY_DIAMOND = ROOT / "templates" / "diamond"
REQUIRED_FILES = ("background.png", "foreground.png", "player_mask.png", "template.json", "preview.png")

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="module")
def qt_app():
    application = QApplication.instance() or QApplication(["standard-tier-tests"])
    yield application


def make_paths(tmp_path: Path) -> AppPaths:
    paths = AppPaths(
        root=ROOT,
        templates=BUILT_INS,
        readme=ROOT / "README.md",
        user_data=tmp_path,
        projects=tmp_path / "projects",
        exports=tmp_path / "exports",
        logs=tmp_path / "logs",
        builder_projects=tmp_path / "builder-projects",
        builder_autosaves=tmp_path / "builder-autosaves",
        builder_backups=tmp_path / "builder-backups",
    )
    paths.ensure_writable_directories()
    return paths


def test_six_standard_tiers_are_discovered_in_required_order():
    service = TemplateService(BUILT_INS)
    discovered = service.discover()
    assert tuple(path.name for path in discovered) == BUILT_IN_TEMPLATE_ORDER
    assert [service.load(path).display_name for path in discovered] == [
        "Pink Diamond", "Diamond", "Amethyst", "Gold", "Silver", "Bronze"
    ]


def test_all_standard_tier_files_dimensions_and_transparent_openings():
    service = TemplateService(BUILT_INS)
    for tier_id in BUILT_IN_TEMPLATE_ORDER:
        directory = BUILT_INS / tier_id
        assert all((directory / filename).is_file() for filename in REQUIRED_FILES)
        template = service.load(tier_id)
        assert template.native_size == (325, 455)
        background = np.asarray(Image.open(directory / "background.png").convert("RGBA"))
        foreground = np.asarray(Image.open(directory / "foreground.png").convert("RGBA"))
        preview = np.asarray(Image.open(directory / "preview.png").convert("RGBA"))
        player_mask = np.asarray(Image.open(directory / "player_mask.png").convert("L"))
        assert background.shape == foreground.shape == preview.shape == (455, 325, 4)
        assert player_mask.shape == (455, 325)
        assert np.count_nonzero(background[:, :, 3]) == 0
        assert set(np.unique(player_mask)).issubset({0, 255})
        opening = player_mask == 255
        assert np.count_nonzero(opening) == 111_504
        assert np.count_nonzero(foreground[:, :, 3][opening]) == 0
        assert np.count_nonzero(preview[:, :, 3][opening]) == 0
        assert np.count_nonzero(foreground[:404, 48, 3]) == 404
        assert np.count_nonzero(foreground[:404, 49, 3]) == 0


def test_new_tiers_have_blank_nameplates_and_source_specific_art_is_absent():
    for tier_id in ("bronze", "silver", "gold", "amethyst"):
        directory = BUILT_INS / tier_id
        foreground = np.asarray(Image.open(directory / "foreground.png").convert("RGBA"))
        mask = np.asarray(Image.open(directory / "player_mask.png").convert("L")) == 255
        # Every source player, logo, medal, and team background was inside the
        # transparent opening and therefore has no surviving RGBA pixel.
        assert np.all(foreground[mask] == 0)
        nameplate = foreground[421:451, 85:321, :3]
        assert np.count_nonzero(np.min(nameplate, axis=2) >= 140) == 0
        report = json.loads((directory / "diagnostics" / "extraction_report.json").read_text(encoding="utf-8"))
        assert report["transparent_center"] is True
        assert report["blank_dynamic_text_regions"] == ["overall", "position", "name"]
        assert report["source_modified"] is False
        assert report["source_resampled"] is False


def test_text_metadata_and_dynamic_text_stay_inside_every_tier():
    service = TemplateService(BUILT_INS)
    renderer = CardRenderer(TEXT_STYLES)
    text = TextPlaceholders("99", "PG", "KENTAVIOUS CALDWELL-POPE")
    for tier_id in BUILT_IN_TEMPLATE_ORDER:
        template = service.load(tier_id)
        for field_name in ("overall", "position", "name"):
            field = template.text_fields[field_name]
            assert 0 <= field["x"] < 325 and 0 <= field["y"] < 455
            assert field["x"] + field["width"] <= 325
            assert field["y"] + field["height"] <= 455
            assert field["text_style"] == "nba2k16_default"
            assert field["alignment"] == "center"
        result = renderer.render(template, None, PlayerTransform(187, 405), text=text)
        assert not result.warnings, tier_id
        assert len(result.text_layouts) == 4
        for layout in result.text_layouts:
            left, top, width, height = layout.bounds
            safe_left, safe_top, safe_width, safe_height = layout.safe_bounds
            assert safe_left <= left and left + width <= safe_left + safe_width, (tier_id, layout.role)
            assert safe_top <= top and top + height <= safe_top + safe_height, (tier_id, layout.role)
        position = next(layout for layout in result.text_layouts if layout.role == "position")
        name = next(layout for layout in result.text_layouts if layout.role == "name")
        assert position.bounds[0] + position.bounds[2] < name.bounds[0]


def test_each_tier_allows_player_over_side_rail_but_protects_nameplate():
    service = TemplateService(BUILT_INS)
    renderer = CardRenderer(TEXT_STYLES)
    player = Image.new("RGBA", (325, 455), (19, 211, 87, 255))
    for tier_id in BUILT_IN_TEMPLATE_ORDER:
        template = service.load(tier_id)
        rendered = renderer.render_for_export(template, player, PlayerTransform(162.5, 455))
        assert rendered.getpixel((200, 200)) == (19, 211, 87, 255)
        assert rendered.getpixel((20, 200)) == (19, 211, 87, 255)
        assert rendered.getpixel((200, 430)) != (19, 211, 87, 255)


def test_tier_switching_preserves_player_source_and_text(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("NBA2K16_CARD_STUDIO_DATA_DIR", str(tmp_path / "data"))
    controller = CardStudioApplication(qt_app, make_paths(tmp_path), logging.getLogger("tier-switch-test"))
    player_path = tmp_path / "player.png"
    Image.new("RGBA", (40, 80), (200, 40, 60, 180)).save(player_path)
    controller.player_source = load_player_image(player_path)
    assert controller.project is not None
    controller.project.player_source_path = str(player_path)
    controller.set_text_fields("94", "SG", "MICHAEL JORDAN")
    original_source = controller.player_source
    for directory in controller.template_service.discover():
        controller._apply_template(directory)
        assert controller.player_source is original_source
        assert controller.project.player_source_path == str(player_path)
        assert (controller.project.text.overall, controller.project.text.position, controller.project.text.name) == (
            "94", "SG", "MICHAEL JORDAN"
        )


def test_project_round_trip_preserves_tier_and_text(tmp_path):
    project = CardProject(
        template=TemplateReference("amethyst", str(BUILT_INS / "amethyst")),
        player_source_path=None,
        player_transform=PlayerTransform(187, 405),
        text=TextPlaceholders("90", "SG", "MICHAEL JORDAN"),
    )
    path = tmp_path / "amethyst.2k16card"
    ProjectService.save(project, path)
    loaded = ProjectService.load(path)
    assert loaded.template.template_id == "amethyst"
    assert (loaded.text.overall, loaded.text.position, loaded.text.name) == ("90", "SG", "MICHAEL JORDAN")
    assert TemplateService(BUILT_INS).load(loaded.template.template_id).display_name == "Amethyst"


def test_built_in_diamond_runtime_pixels_match_completed_diamond():
    for filename in ("background.png", "foreground.png", "player_mask.png", "preview.png"):
        installed = np.asarray(Image.open(BUILT_INS / "diamond" / filename))
        completed = np.asarray(Image.open(LEGACY_DIAMOND / filename))
        assert np.array_equal(installed, completed), filename
    installed_json = json.loads((BUILT_INS / "diamond" / "template.json").read_text(encoding="utf-8"))
    completed_json = json.loads((LEGACY_DIAMOND / "template.json").read_text(encoding="utf-8"))
    installed_json.pop("sort_order")
    completed_json.pop("sort_order")
    assert installed_json == completed_json


def test_diamond_ovr_divider_is_restored_from_the_authentic_source():
    source_path = ROOT.parent / "data" / "card-images" / "9857-kareem-abdul-jabbar.png"
    if not source_path.is_file():
        pytest.skip("private source-card provenance fixture is not included in the public repository")
    source = np.asarray(Image.open(source_path).convert("RGBA"))
    foreground = np.asarray(Image.open(BUILT_INS / "diamond" / "foreground.png").convert("RGBA"))
    assert np.array_equal(foreground[53:58, 11:46], source[53:58, 11:46])
    assert np.count_nonzero(np.min(foreground[53:58, 11:46, :3], axis=2) >= 120) >= 70


def test_pink_diamond_has_the_same_neutral_ovr_divider():
    diamond = np.asarray(Image.open(BUILT_INS / "diamond" / "foreground.png").convert("RGBA"))
    pink = np.asarray(Image.open(BUILT_INS / "pink_diamond" / "foreground.png").convert("RGBA"))
    assert np.array_equal(pink[54:57, 13:45], diamond[54:57, 13:45])
    assert np.all(pink[54, 14:44, :3] >= 240)


def test_light_ovr_panels_have_tier_specific_black_bitmap_shadows():
    service = TemplateService(BUILT_INS)
    for tier_id in ("bronze", "silver", "gold"):
        overall = service.load(tier_id).text_fields["overall"]
        assert overall["shadow"] == {"offset_x": 1, "offset_y": 1, "color": [0, 0, 0, 176]}
        assert overall["label"]["shadow"] == overall["shadow"]
    for tier_id in ("amethyst", "diamond", "pink_diamond"):
        overall = service.load(tier_id).text_fields["overall"]
        assert "shadow" not in overall
        assert "shadow" not in overall["label"]


def test_ovr_rating_is_optically_centered_under_label_for_every_tier():
    service = TemplateService(BUILT_INS)
    renderer = CardRenderer(TEXT_STYLES)
    for tier_id in BUILT_IN_TEMPLATE_ORDER:
        template = service.load(tier_id)
        assert template.text_fields["overall"]["label"]["x"] == 15
        for rating in ("90", "91"):
            result = renderer.render(
                template,
                None,
                PlayerTransform(162.5, 455),
                text=TextPlaceholders(overall=rating),
            )
            label, number = [layout for layout in result.text_layouts if layout.role == "overall"]
            label_center = label.bounds[0] + (label.bounds[2] - 1) / 2
            number_center = number.bounds[0] + (number.bounds[2] - 1) / 2
            assert abs(label_center - number_center) <= 0.5, (tier_id, rating)


def test_packaged_preview_equals_blank_export_for_every_tier():
    service = TemplateService(BUILT_INS)
    renderer = CardRenderer(TEXT_STYLES)
    for tier_id in BUILT_IN_TEMPLATE_ORDER:
        template = service.load(tier_id)
        preview = np.asarray(Image.open(BUILT_INS / tier_id / "preview.png").convert("RGBA"))
        exported = np.asarray(
            renderer.render_for_export(template, None, PlayerTransform(187, 405), TextPlaceholders())
        )
        assert np.array_equal(preview, exported), tier_id
