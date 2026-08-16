import numpy as np
from PIL import Image

from app.models.player_art_model import PlayerTransform
from app.models.logo_model import LogoPlacement
from app.rendering.card_renderer import CardRenderer, RenderOptions
from app.services.template_service import TemplateService


def load_template(template_factory, tmp_path):
    return TemplateService(tmp_path).load(template_factory())


def test_output_dimensions_and_rgba(template_factory, tmp_path):
    template = load_template(template_factory, tmp_path)
    player = Image.new("RGBA", (4, 6), (0, 255, 0, 255))
    result = CardRenderer().render(template, player, PlayerTransform(4, 9)).image
    assert result.size == (8, 10)
    assert result.mode == "RGBA"


def test_mask_background_and_foreground_order(template_factory, tmp_path):
    template = load_template(template_factory, tmp_path)
    player = Image.new("RGBA", (8, 10), (0, 255, 0, 255))
    result = CardRenderer().render(template, player, PlayerTransform(4, 10)).image
    assert result.getpixel((0, 0)) == (20, 30, 40, 255)  # masked player is hidden
    assert result.getpixel((0, 3)) == (0, 255, 0, 255)  # player can overlap the side rail
    assert result.getpixel((3, 3)) == (0, 255, 0, 255)  # player over background
    assert result.getpixel((4, 5)) == (0, 255, 0, 255)  # player over frame art
    assert result.getpixel((3, 9)) == (20, 30, 40, 255)  # bottom nameplate row stays protected


def test_off_canvas_content_clips_safely(template_factory, tmp_path):
    template = load_template(template_factory, tmp_path)
    player = Image.new("RGBA", (5, 5), (0, 255, 0, 255))
    renderer = CardRenderer()
    partially = renderer.render(template, player, PlayerTransform(-1, 3)).image
    outside = renderer.render(template, player, PlayerTransform(-100, -100)).image
    assert partially.size == template.native_size
    assert outside.size == template.native_size


def test_diagnostics_do_not_affect_export(template_factory, tmp_path):
    template = load_template(template_factory, tmp_path)
    player = Image.new("RGBA", (4, 6), (0, 255, 0, 255))
    renderer = CardRenderer()
    normal = renderer.render_for_export(template, player, PlayerTransform(4, 9))
    diagnostic = renderer.render(
        template, player, PlayerTransform(4, 9), RenderOptions(False, False, False, "overlay")
    ).image
    exported_again = renderer.render_for_export(template, player, PlayerTransform(4, 9))
    assert np.array_equal(np.asarray(normal), np.asarray(exported_again))
    assert not np.array_equal(np.asarray(normal), np.asarray(diagnostic))


def test_repeated_render_is_pixel_identical(template_factory, tmp_path):
    template = load_template(template_factory, tmp_path)
    player = Image.new("RGBA", (7, 9), (50, 220, 90, 180))
    transform = PlayerTransform(3.5, 8.0, 0.73, 17.5, True)
    renderer = CardRenderer()
    first = np.asarray(renderer.render_for_export(template, player, transform))
    second = np.asarray(renderer.render_for_export(template, player, transform))
    assert np.array_equal(first, second)


def test_logo_renders_below_player_and_foreground(template_factory, tmp_path):
    template = load_template(template_factory, tmp_path)
    logo_image = Image.new("RGBA", (4, 4), (255, 0, 0, 255))
    player = Image.new("RGBA", (4, 6), (0, 255, 0, 255))
    logo = LogoPlacement("current", "test.png")
    result = CardRenderer().render_for_export(
        template,
        player,
        PlayerTransform(4, 9),
        logo_image=logo_image,
        logo=logo,
    )
    assert result.getpixel((3, 2)) == (255, 0, 0, 255)  # logo over background
    assert result.getpixel((3, 3)) == (0, 255, 0, 255)  # player over logo
    assert result.getpixel((4, 5)) == (0, 255, 0, 255)  # player over frame and logo


def test_team_logo_uses_fixed_reference_transform_without_mutating_source(template_factory, tmp_path):
    template = load_template(template_factory, tmp_path)
    source = Image.new("RGBA", (100, 50), (255, 0, 0, 255))
    renderer = CardRenderer()
    result = renderer.render_for_export(
        template, None, PlayerTransform(4, 9),
        logo_image=source, logo=LogoPlacement("current", "test.png"),
    )
    assert result.getpixel((3, 2)) == (255, 0, 0, 255)
    assert source.size == (100, 50)


def test_background_team_frame_player_and_promotion_depth(template_factory, tmp_path):
    template = load_template(template_factory, tmp_path)
    background = Image.new("RGBA", (1024, 1024), (80, 90, 100, 255))
    team = Image.new("RGBA", (1024, 1024), (255, 0, 0, 255))
    player = Image.new("RGBA", (8, 10), (0, 255, 0, 255))
    promotion = Image.new("RGBA", (256, 256), (255, 255, 0, 255))
    result = CardRenderer().render_for_export(
        template,
        player,
        PlayerTransform(4, 10),
        logo_image=team,
        logo=LogoPlacement("current", "test.png"),
        background_image=background,
        promotion_image=promotion,
    )
    assert result.getpixel((0, 0)) == (20, 30, 40, 255)  # template background above recovered art
    assert result.getpixel((3, 3)) == (0, 255, 0, 255)  # player above team/frame
    assert result.getpixel((2, 7)) == (255, 255, 0, 255)  # promotion is topmost
