"""Small RGBA compositing primitives used by the renderer."""

from __future__ import annotations

from PIL import Image, ImageChops


def place_rgba(canvas_size: tuple[int, int], image: Image.Image, left: int, top: int) -> Image.Image:
    """Place an RGBA image on a transparent canvas, safely clipping overflow."""
    canvas = Image.new("RGBA", canvas_size, (0, 0, 0, 0))
    canvas.alpha_composite(image.convert("RGBA"), (left, top))
    return canvas


def apply_mask(player_layer: Image.Image, mask: Image.Image) -> Image.Image:
    """Multiply source alpha by the template's native-resolution L mask."""
    rgba = player_layer.convert("RGBA")
    clipped = rgba.copy()
    clipped.putalpha(ImageChops.multiply(rgba.getchannel("A"), mask.convert("L")))
    return clipped


def composite_layers(*layers: Image.Image) -> Image.Image:
    if not layers:
        raise ValueError("At least one layer is required")
    result = Image.new("RGBA", layers[0].size, (0, 0, 0, 0))
    for layer in layers:
        result = Image.alpha_composite(result, layer.convert("RGBA"))
    return result
