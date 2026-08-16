"""Lossless source-image loading that preserves the untouched original."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.constants import SUPPORTED_PLAYER_FORMATS
from app.utilities.validation import ImageLoadError


@dataclass(frozen=True, slots=True)
class LoadedPlayerImage:
    image: Image.Image
    source_path: Path
    original_size: tuple[int, int]
    has_transparency: bool
    warning: str | None = None


def image_has_transparency(image: Image.Image) -> bool:
    if image.mode in {"RGBA", "LA"}:
        alpha = image.getchannel("A")
        minimum, _maximum = alpha.getextrema()
        return minimum < 255
    return "transparency" in image.info


def load_player_image(path: Path) -> LoadedPlayerImage:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_PLAYER_FORMATS:
        raise ImageLoadError(f"Unsupported player image format: {suffix or '(none)'}")
    try:
        with Image.open(path) as opened:
            opened.load()
            has_transparency = image_has_transparency(opened)
            original_size = opened.size
            rgba = opened.convert("RGBA").copy()
    except (OSError, UnidentifiedImageError) as exc:
        raise ImageLoadError(f"Could not decode player image '{path.name}': {exc}") from exc
    warning = None
    if suffix in {".jpg", ".jpeg"}:
        warning = "JPEG images do not contain transparency. Use Remove Background to create a local cutout."
    elif not has_transparency:
        warning = "This image has no transparent pixels. Use Remove Background to create a local cutout."
    return LoadedPlayerImage(rgba, path.resolve(), original_size, has_transparency, warning)
