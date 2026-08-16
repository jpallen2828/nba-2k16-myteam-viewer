from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from app.models.player_art_model import PlayerTransform
from app.rendering.card_renderer import CardRenderer
from app.services.template_service import TemplateService


STUDIO_ROOT = Path(__file__).resolve().parents[1]
DIAMOND_ROOT = STUDIO_ROOT / "templates" / "diamond"
SOURCE = STUDIO_ROOT.parent / "data" / "card-images" / "9857-kareem-abdul-jabbar.png"


def test_diamond_player_opening_is_fully_transparent_and_renders_player_art():
    template = TemplateService(STUDIO_ROOT / "templates").load("diamond")
    background = np.asarray(Image.open(DIAMOND_ROOT / "background.png").convert("RGBA"))
    foreground = np.asarray(Image.open(DIAMOND_ROOT / "foreground.png").convert("RGBA"))
    player_mask = np.asarray(Image.open(DIAMOND_ROOT / "player_mask.png").convert("L"))
    preview = np.asarray(Image.open(DIAMOND_ROOT / "preview.png").convert("RGBA"))
    opening = player_mask == 255

    assert np.count_nonzero(background[:, :, 3]) == 0
    assert np.count_nonzero(foreground[:, :, 3][opening]) == 0
    assert np.count_nonzero(preview[:, :, 3][opening]) == 0
    assert set(np.unique(player_mask)).issubset({0, 255})
    assert np.count_nonzero(foreground[:404, 49, 3]) == 0
    assert np.count_nonzero(foreground[:404, 48, 3]) == 404

    player = Image.new("RGBA", template.native_size, (18, 220, 70, 255))
    rendered = CardRenderer().render_for_export(
        template,
        player,
        PlayerTransform(template.canvas.width / 2, template.canvas.height),
    )
    assert rendered.getpixel((200, 200)) == (18, 220, 70, 255)


def test_diamond_name_cleanup_does_not_touch_the_left_corner():
    if not SOURCE.is_file():
        pytest.skip("private source-card provenance fixture is not included in the public repository")
    source = np.asarray(Image.open(SOURCE).convert("RGBA"))
    foreground = np.asarray(Image.open(DIAMOND_ROOT / "foreground.png").convert("RGBA"))

    assert np.array_equal(foreground[421:451, 50:68], source[421:451, 50:68])

    source_rgb = source[:, :, :3].astype(np.int16)
    cyan_corner = (
        (source_rgb[:, :, 2] > source_rgb[:, :, 0] + 18)
        & (source_rgb[:, :, 1] > source_rgb[:, :, 0] + 8)
        & (source_rgb[:, :, 2] > 110)
    )
    protected = np.zeros(cyan_corner.shape, dtype=bool)
    protected[421:451, 68:82] = cyan_corner[421:451, 68:82]
    assert np.array_equal(foreground[protected], source[protected])
    assert foreground[448, 72].tolist() == source[448, 72].tolist()
