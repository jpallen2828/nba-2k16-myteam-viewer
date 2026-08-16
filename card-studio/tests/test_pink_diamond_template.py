from pathlib import Path

import numpy as np
from PIL import Image

from app.models.player_art_model import PlayerTransform
from app.rendering.card_renderer import CardRenderer
from app.services.template_service import TemplateService


STUDIO_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = STUDIO_ROOT / "templates" / "pink_diamond"
EXPECTED_SOURCE_HASH = "FD206E65A6C73C1507FCAD47C8A412C5550DCC98201E6819EA91955EE15ED7D7"


def test_pink_diamond_is_a_valid_installed_template():
    template = TemplateService(STUDIO_ROOT / "templates").load("pink_diamond")

    assert template.display_name == "Pink Diamond"
    assert template.native_size == (325, 455)
    assert template.extraction["source_sha256"] == EXPECTED_SOURCE_HASH


def test_pink_diamond_layers_preserve_transparency_with_source_ovr_divider():
    background = np.asarray(Image.open(TEMPLATE_ROOT / "background.png").convert("RGBA"))
    foreground = np.asarray(Image.open(TEMPLATE_ROOT / "foreground.png").convert("RGBA"))
    preview = np.asarray(Image.open(TEMPLATE_ROOT / "preview.png").convert("RGBA"))
    player_mask = np.asarray(Image.open(TEMPLATE_ROOT / "player_mask.png").convert("L"))

    assert np.count_nonzero(background[:, :, 3]) == 0
    assert np.array_equal(preview, foreground)
    assert np.array_equal(player_mask, np.where(foreground[:, :, 3] == 0, 255, 0).astype(np.uint8))
    assert np.count_nonzero(foreground[:, :, 3][player_mask == 255]) == 0
    template = TemplateService(STUDIO_ROOT / "templates").load("pink_diamond")
    assert template.extraction["ovr_divider_source_rect"] == [13, 54, 45, 57]
    assert template.extraction["source_patched_pixel_count"] == 96


def test_pink_diamond_renders_player_art_through_the_opening():
    template = TemplateService(STUDIO_ROOT / "templates").load("pink_diamond")
    player = Image.new("RGBA", template.native_size, (230, 30, 175, 255))
    rendered = CardRenderer().render_for_export(
        template,
        player,
        PlayerTransform(template.canvas.width / 2, template.canvas.height),
    )

    assert rendered.getpixel((200, 200)) == (230, 30, 175, 255)
