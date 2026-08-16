from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from app.models.player_art_model import PlayerTransform
from app.models.project_model import CardProject, TemplateReference, TextPlaceholders
from app.rendering.card_renderer import CardRenderer
from app.services.project_service import ProjectService
from app.services.template_service import TemplateService
from app.text.bitmap_text import BitmapTextRenderer
from app.text.glyph_atlas import GlyphAtlas
from app.text.normalization import normalize_name, normalize_overall, normalize_position


ROOT = Path(__file__).resolve().parents[1]
STYLE = ROOT / "assets" / "text_styles" / "nba2k16_default"
REQUIRED_TEXT = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 .-'")


def test_packaged_atlases_have_complete_approved_coverage():
    name = GlyphAtlas.load(STYLE, "name")
    position = GlyphAtlas.load(STYLE, "position")
    overall = GlyphAtlas.load(STYLE, "overall")
    assert not name.missing("".join(REQUIRED_TEXT))
    assert not position.missing("".join(REQUIRED_TEXT))
    assert not overall.missing("0123456789OVR")
    assert all(glyph.approved for glyph in name.glyphs.values())
    assert all(glyph.source_reference for glyph in name.glyphs.values())


def test_input_normalization_is_uppercase_bounded_and_predictable():
    assert normalize_name("  c.j.   mccollum  ") == "C.J. MCCOLLUM"
    assert normalize_name("shaquille o'neal") == "SHAQUILLE O'NEAL"
    assert normalize_name(" '89 michael jordan ") == "'89 MICHAEL JORDAN"
    assert normalize_position(" pg ") == "PG"
    assert normalize_position("p/f") == "PF"
    assert normalize_overall("097") == "97"
    assert normalize_overall("125") == "99"
    assert normalize_overall("none") == ""


def test_measurement_uses_approved_kerning_and_tracking():
    atlas = GlyphAtlas.load(STYLE, "name")
    unkerned = atlas.glyphs["V"].advance + atlas.glyphs["A"].rect[2]
    assert atlas.kerning["VA"] < 0
    assert atlas.measure("VA") < unkerned
    assert atlas.measure("METTA WORLD PEACE", -1.0) < atlas.measure("METTA WORLD PEACE", 0.0)


def test_name_fitter_tightens_tracking_then_scales_without_clipping():
    renderer = BitmapTextRenderer(ROOT / "assets" / "text_styles")
    canvas = Image.new("RGBA", (325, 455))
    field = {
        "x": 70,
        "y": 417,
        "width": 125,
        "height": 35,
        "baseline": 438,
        "source_baseline": 16,
        "maximum_width": 120,
        "minimum_tracking": -1.5,
        "preferred_tracking": 0.0,
        "min_scale": 0.5,
    }
    layout = renderer.render_field(canvas, "KAREEM ABDUL-JABBAR", "nba2k16_default", "name", field)
    assert layout.fitted
    assert layout.tracking == -1.5
    assert 0.5 <= layout.scale < 1.0
    left, _top, width, _height = layout.bounds
    safe_left, _safe_top, safe_width, _safe_height = layout.safe_bounds
    assert left >= safe_left
    assert left + width <= safe_left + safe_width


def test_diamond_text_fields_stay_inside_separate_safe_regions():
    template = TemplateService(ROOT / "templates").load("diamond")
    renderer = CardRenderer(ROOT / "assets" / "text_styles")
    text = TextPlaceholders("99", "PG", "MICHAEL CARTER-WILLIAMS")
    result = renderer.render(template, None, PlayerTransform(187, 405), text=text)
    layouts = {layout.role: layout for layout in result.text_layouts if layout.text != "OVR"}
    assert not result.warnings
    for layout in layouts.values():
        left, top, width, height = layout.bounds
        safe_left, safe_top, safe_width, safe_height = layout.safe_bounds
        assert left >= safe_left and left + width <= safe_left + safe_width
        assert top >= safe_top and top + height <= safe_top + safe_height
    position = layouts["position"]
    name = layouts["name"]
    assert position.bounds[0] + position.bounds[2] < name.bounds[0]


def test_reference_and_long_database_names_all_fit_the_real_nameplate():
    template = TemplateService(ROOT / "templates").load("diamond")
    renderer = BitmapTextRenderer(ROOT / "assets" / "text_styles")
    field = template.text_fields["name"]
    names = (
        "'89 MICHAEL JORDAN",
        "'14 KAWHI LEONARD",
        "KAREEM ABDUL-JABBAR",
        "C.J. MCCOLLUM",
        "SHAQUILLE O'NEAL",
        "KARL-ANTHONY TOWNS",
        "METTA WORLD PEACE",
        "KENTAVIOUS CALDWELL-POPE",
        "MICHAEL CARTER-WILLIAMS",
        "RONDAE HOLLIS-JEFFERSON",
        "GIANNIS ANTETOKOUNMPO",
    )
    for name in names:
        canvas = Image.new("RGBA", template.native_size)
        layout = renderer.render_field(canvas, name, "nba2k16_default", "name", field)
        assert layout.fitted, name
        left, _top, width, _height = layout.bounds
        safe_left, _safe_top, safe_width, _safe_height = layout.safe_bounds
        assert safe_left <= left and left + width <= safe_left + safe_width, name


def test_all_required_name_characters_render_and_center_without_clipping():
    template = TemplateService(ROOT / "assets" / "built_in_templates").load("diamond")
    renderer = BitmapTextRenderer(ROOT / "assets" / "text_styles")
    field = template.text_fields["name"]
    examples = (
        "'89 MICHAEL JORDAN",
        "'14 KAWHI LEONARD",
        "C.J. MCCOLLUM",
        "SHAQUILLE O'NEAL",
        "KARL-ANTHONY TOWNS",
        "KENTAVIOUS CALDWELL-POPE",
    )
    for value in examples:
        canvas = Image.new("RGBA", template.native_size)
        layout = renderer.render_field(canvas, value, "nba2k16_default", "name", field)
        assert layout.fitted and not layout.missing_glyphs, value
        left, _top, width, _height = layout.bounds
        safe_left, _safe_top, safe_width, _safe_height = layout.safe_bounds
        assert safe_left <= left and left + width <= safe_left + safe_width, value
        assert abs((left + width / 2) - (safe_left + safe_width / 2)) <= 0.5, value


def test_overall_position_and_name_use_centered_tier_layouts():
    service = TemplateService(ROOT / "assets" / "built_in_templates")
    renderer = CardRenderer(ROOT / "assets" / "text_styles")
    for template_id in ("bronze", "silver", "gold", "amethyst", "diamond", "pink_diamond"):
        template = service.load(template_id)
        result = renderer.render(
            template,
            None,
            PlayerTransform(187, 405),
            text=TextPlaceholders("97", "C", "C.J. MCCOLLUM"),
        )
        assert not result.warnings
        for layout in result.text_layouts:
            left, _top, width, _height = layout.bounds
            safe_left, _safe_top, safe_width, _safe_height = layout.safe_bounds
            assert abs((left + width / 2) - (safe_left + safe_width / 2)) <= 0.5, (template_id, layout.text)


def test_preview_render_is_pixel_identical_to_export_with_dynamic_text():
    template = TemplateService(ROOT / "assets" / "built_in_templates").load("pink_diamond")
    renderer = CardRenderer(ROOT / "assets" / "text_styles")
    text = TextPlaceholders("97", "PG", "KARL-ANTHONY TOWNS")
    preview = renderer.render(template, None, PlayerTransform(187, 405), text=text).image
    exported = renderer.render_for_export(template, None, PlayerTransform(187, 405), text=text)
    assert np.array_equal(np.asarray(preview), np.asarray(exported))


def test_bitmap_shadow_uses_glyph_alpha_without_changing_layout():
    renderer = BitmapTextRenderer(ROOT / "assets" / "text_styles")
    field = {
        "x": 10, "y": 24, "width": 36, "height": 29,
        "alignment": "center", "baseline": 49, "source_baseline": 23,
        "safe_inset_left": 2, "safe_inset_right": 2, "safe_inset_top": 2, "safe_inset_bottom": 1,
        "maximum_width": 32, "min_scale": 0.72,
    }
    plain = Image.new("RGBA", (60, 70))
    plain_layout = renderer.render_field(plain, "87", "nba2k16_default", "overall", field)
    shadowed = Image.new("RGBA", (60, 70))
    shadow_field = dict(field, shadow={"offset_x": 1, "offset_y": 1, "color": [0, 0, 0, 176]})
    shadow_layout = renderer.render_field(shadowed, "87", "nba2k16_default", "overall", shadow_field)
    assert shadow_layout.bounds == plain_layout.bounds
    added = (np.asarray(shadowed)[:, :, 3] > np.asarray(plain)[:, :, 3])
    assert np.count_nonzero(added) > 0
    assert np.count_nonzero(np.max(np.asarray(shadowed)[:, :, :3][added], axis=1) == 0) > 0


def test_overall_one_uses_clean_unobstructed_source_crop():
    metadata = json.loads((STYLE / "overall_atlas.json").read_text(encoding="utf-8"))
    glyph = metadata["glyphs"]["1"]
    assert glyph["source_reference"] == "data/card-images/358-steve-nash.png"
    assert glyph["rejected_artifact_pixels"] == 0
    x, y, width, height = glyph["rect"]
    alpha = np.asarray(Image.open(STYLE / "overall_atlas.png").convert("RGBA"))[y : y + height, x : x + width, 3]
    # Regression guard for the disconnected hand/finger pixels formerly
    # visible down the lower-left side of the numeral.
    assert np.count_nonzero(alpha[8:, :5]) == 0


def test_dynamic_text_render_is_pixel_identical_and_changes_card_pixels():
    template = TemplateService(ROOT / "templates").load("pink_diamond")
    renderer = CardRenderer(ROOT / "assets" / "text_styles")
    transform = PlayerTransform(187, 405)
    text = TextPlaceholders("97", "C", "KARL-ANTHONY TOWNS")
    first = np.asarray(renderer.render_for_export(template, None, transform, text))
    second = np.asarray(renderer.render_for_export(template, None, transform, text))
    blank = np.asarray(renderer.render_for_export(template, None, transform, TextPlaceholders()))
    assert np.array_equal(first, second)
    assert not np.array_equal(first, blank)


def test_project_round_trip_preserves_text_style_fit_tracking_and_offsets(tmp_path):
    project = CardProject(
        template=TemplateReference("diamond", str(ROOT / "templates" / "diamond")),
        player_source_path=None,
        player_transform=PlayerTransform(187, 405),
        text=TextPlaceholders(
            overall="97",
            position="pg",
            name="c.j.  mccollum",
            style="nba2k16_default",
            fitted_scale={"name": 0.82},
            fitted_tracking={"name": -1.25},
            offsets={"name": [1.0, -2.0]},
        ),
    )
    path = tmp_path / "text.2k16card"
    ProjectService.save(project, path)
    loaded = ProjectService.load(path)
    assert loaded.text.overall == "97"
    assert loaded.text.position == "PG"
    assert loaded.text.name == "C.J. MCCOLLUM"
    assert loaded.text.style == "nba2k16_default"
    assert loaded.text.fitted_scale == {"name": 0.82}
    assert loaded.text.fitted_tracking == {"name": -1.25}
    assert loaded.text.offsets == {"name": [1.0, -2.0]}


def test_missing_glyph_produces_warning_and_no_substitute(tmp_path):
    style = tmp_path / "nba2k16_default"
    style.mkdir()
    source_meta = json.loads((STYLE / "name_atlas.json").read_text(encoding="utf-8"))
    del source_meta["glyphs"]["Q"]
    (style / "name_atlas.json").write_text(json.dumps(source_meta), encoding="utf-8")
    Image.open(STYLE / "name_atlas.png").save(style / "name_atlas.png")
    renderer = BitmapTextRenderer(tmp_path)
    canvas = Image.new("RGBA", (200, 50))
    layout = renderer.render_field(
        canvas,
        "QUINCY",
        "nba2k16_default",
        "name",
        {"x": 0, "y": 0, "width": 200, "height": 40, "baseline": 25, "maximum_width": 200, "min_scale": 0.5},
    )
    assert not layout.fitted
    assert layout.missing_glyphs == ("Q",)
    assert "Missing authentic name glyphs" in layout.warning
    assert canvas.getbbox() is None


def test_extraction_report_has_no_missing_required_glyphs_and_sources_are_not_bundled():
    report = json.loads((STYLE / "extraction_report.json").read_text(encoding="utf-8"))
    assert report["source_cards_modified"] is False
    assert all(not role["missing"] for role in report["roles"].values())
    assert "assets" in (ROOT / "NBA2K16CardStudio.spec").read_text(encoding="utf-8")
    assert not (STYLE / "source_cards").exists()
