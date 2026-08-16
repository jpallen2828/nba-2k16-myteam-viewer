"""Lossless RGB-plus-mask cutout composition and mask serialization."""

from __future__ import annotations

import base64
import io

import numpy as np
from PIL import Image

from app.background_removal.exceptions import BackgroundRemovalError


def apply_alpha_mask(original: Image.Image, mask: Image.Image) -> Image.Image:
    if original.size != mask.size:
        raise BackgroundRemovalError(
            f"Mask dimensions {mask.size} do not match the original image {original.size}."
        )
    rgba = np.asarray(original.convert("RGBA"), dtype=np.uint8).copy()
    alpha = np.asarray(mask.convert("L"), dtype=np.uint8)
    # Preserve any transparency already present in the source while leaving RGB untouched.
    rgba[:, :, 3] = np.minimum(rgba[:, :, 3], alpha)
    return Image.fromarray(rgba, mode="RGBA")


def encode_mask_png(mask: Image.Image) -> str:
    stream = io.BytesIO()
    mask.convert("L").save(stream, format="PNG", optimize=True)
    return base64.b64encode(stream.getvalue()).decode("ascii")


def decode_mask_png(encoded: str, expected_size: tuple[int, int] | None = None) -> Image.Image:
    try:
        payload = base64.b64decode(encoded, validate=True)
        with Image.open(io.BytesIO(payload)) as opened:
            opened.load()
            mask = opened.convert("L").copy()
    except Exception as exc:
        raise BackgroundRemovalError(f"The saved alpha mask could not be decoded: {exc}") from exc
    if expected_size is not None and mask.size != expected_size:
        raise BackgroundRemovalError(
            f"Saved mask dimensions {mask.size} do not match the relinked image {expected_size}."
        )
    return mask
