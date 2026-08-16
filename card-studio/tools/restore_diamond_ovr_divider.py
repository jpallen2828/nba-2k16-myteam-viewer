"""Restore the Diamond OVR divider and install it on Pink Diamond."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path

import numpy as np
from PIL import Image


STUDIO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = STUDIO_ROOT.parent / "data" / "card-images" / "9857-kareem-abdul-jabbar.png"
EXPECTED_SOURCE_SHA256 = "67B387F3CC598770CB0ECA832788FB1C3F5C32B9674C99D9F29B79F7A6856BB7"
TARGETS = (
    STUDIO_ROOT / "templates" / "diamond",
    STUDIO_ROOT / "assets" / "built_in_templates" / "diamond",
)
PINK_TARGETS = (
    STUDIO_ROOT / "templates" / "pink_diamond",
    STUDIO_ROOT / "assets" / "built_in_templates" / "pink_diamond",
)
# The divider and its native bevel/shadow, immediately below the numeric OVR.
DIVIDER_BOX = (11, 53, 46, 58)
# Only the neutral three-row bar is transferred to Pink Diamond; none of the
# cyan Diamond panel/background pixels are included.
NEUTRAL_DIVIDER_BOX = (13, 54, 45, 57)


def restore() -> None:
    digest = sha256(SOURCE.read_bytes()).hexdigest().upper()
    if digest != EXPECTED_SOURCE_SHA256:
        raise RuntimeError(f"Diamond source hash changed: {digest}")
    with Image.open(SOURCE) as opened:
        source = np.asarray(opened.convert("RGBA"), dtype=np.uint8)
    left, top, right, bottom = DIVIDER_BOX
    for directory in TARGETS:
        for filename in ("foreground.png", "preview.png"):
            path = directory / filename
            with Image.open(path) as opened:
                target = np.asarray(opened.convert("RGBA"), dtype=np.uint8).copy()
            target[top:bottom, left:right] = source[top:bottom, left:right]
            Image.fromarray(target, "RGBA").save(path, "PNG", optimize=False)

    diamond_path = TARGETS[0] / "foreground.png"
    with Image.open(diamond_path) as opened:
        diamond = np.asarray(opened.convert("RGBA"), dtype=np.uint8)
    pink_left, pink_top, pink_right, pink_bottom = NEUTRAL_DIVIDER_BOX
    for directory in PINK_TARGETS:
        for filename in ("foreground.png", "preview.png"):
            path = directory / filename
            with Image.open(path) as opened:
                target = np.asarray(opened.convert("RGBA"), dtype=np.uint8).copy()
            target[pink_top:pink_bottom, pink_left:pink_right] = diamond[
                pink_top:pink_bottom, pink_left:pink_right
            ]
            Image.fromarray(target, "RGBA").save(path, "PNG", optimize=False)


if __name__ == "__main__":
    restore()
    print(f"Restored Diamond OVR divider from {SOURCE.name} at {DIVIDER_BOX}")
    print(f"Installed neutral OVR divider on Pink Diamond at {NEUTRAL_DIVIDER_BOX}")
