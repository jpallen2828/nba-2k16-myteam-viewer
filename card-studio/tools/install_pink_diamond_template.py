"""Install the user-supplied transparent Pink Diamond border as a tier."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path

import numpy as np
from PIL import Image


STUDIO_ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(r"C:\Users\James\Downloads\New PC media files\images\2k16 custom pink diamond boarder.png")
TARGET = STUDIO_ROOT / "templates" / "pink_diamond"
DIAMOND_FRAME = STUDIO_ROOT / "templates" / "diamond" / "foreground.png"
EXPECTED_SHA256 = "FD206E65A6C73C1507FCAD47C8A412C5550DCC98201E6819EA91955EE15ED7D7"
WIDTH, HEIGHT = 325, 455
DIVIDER_BOX = (13, 54, 45, 57)


def text_fields() -> dict:
    return {
        "overall": {
            "x": 10, "y": 24, "width": 36, "height": 29,
            "alignment": "center", "vertical_alignment": "center", "baseline": 49, "source_baseline": 23,
            "safe_inset_left": 2, "safe_inset_right": 2, "safe_inset_top": 2, "safe_inset_bottom": 1,
            "force_uppercase": True, "fit_mode": "scale_to_fit", "max_width": 32,
            "maximum_width": 32, "min_scale": 0.72, "preferred_tracking": 0.0, "minimum_tracking": -1.0,
            "text_style": "nba2k16_default",
            "label": {
                "x": 15, "y": 0, "width": 27, "height": 25, "alignment": "center",
                "baseline": 23, "source_baseline": 23, "maximum_width": 27, "min_scale": 1.0,
            },
            "expected_color": [244, 247, 246, 255], "clean": True,
            "notes": "Blank centered numeric OVR area.",
        },
        "position": {
            "x": 13, "y": 416, "width": 26, "height": 35,
            "alignment": "center", "vertical_alignment": "center", "baseline": 438, "source_baseline": 16,
            "safe_inset_left": 1, "safe_inset_right": 1, "safe_inset_top": 3, "safe_inset_bottom": 3,
            "force_uppercase": True, "fit_mode": "scale_to_fit", "max_width": 24,
            "maximum_width": 24, "min_scale": 0.68, "preferred_tracking": 0.0, "minimum_tracking": -1.0,
            "text_style": "nba2k16_default",
            "expected_color": [242, 244, 239, 255], "clean": True,
            "notes": "Centered one- or two-letter position inside the circular badge.",
        },
        "name": {
            "x": 68, "y": 417, "width": 253, "height": 35,
            "alignment": "center", "vertical_alignment": "center", "baseline": 438, "source_baseline": 16,
            "safe_inset_left": 2, "safe_inset_right": 8, "safe_inset_top": 4, "safe_inset_bottom": 3,
            "force_uppercase": True, "fit_mode": "tighten_tracking_then_scale", "max_width": 244,
            "maximum_width": 243, "min_scale": 0.62, "preferred_tracking": 0.0, "minimum_tracking": -1.0,
            "text_style": "nba2k16_default",
            "expected_color": [244, 247, 246, 255], "clean": True,
            "notes": "Centered nameplate field protected from the separate Pink Diamond corner.",
        },
    }


def main() -> None:
    if not SOURCE.is_file():
        raise FileNotFoundError(SOURCE)
    digest = sha256(SOURCE.read_bytes()).hexdigest().upper()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"Pink Diamond source hash changed: {digest}")
    with Image.open(SOURCE) as opened:
        if opened.size != (WIDTH, HEIGHT) or opened.mode != "RGBA":
            raise RuntimeError(f"Expected {WIDTH}x{HEIGHT} RGBA; got {opened.size} {opened.mode}")
        foreground = np.asarray(opened, dtype=np.uint8).copy()

    with Image.open(DIAMOND_FRAME) as opened:
        diamond = np.asarray(opened.convert("RGBA"), dtype=np.uint8)
    left, top, right, bottom = DIVIDER_BOX
    foreground[top:bottom, left:right] = diamond[top:bottom, left:right]

    alpha = foreground[:, :, 3]
    if set(np.unique(alpha).tolist()) != {0, 255}:
        raise RuntimeError("Pink Diamond source must use hard transparent/opaque alpha")
    player_mask = np.where(alpha == 0, 255, 0).astype(np.uint8)
    background = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)

    TARGET.mkdir(parents=True, exist_ok=True)
    Image.fromarray(background, "RGBA").save(TARGET / "background.png", "PNG", optimize=False)
    Image.fromarray(foreground, "RGBA").save(TARGET / "foreground.png", "PNG", optimize=False)
    Image.fromarray(player_mask, "L").save(TARGET / "player_mask.png", "PNG", optimize=False)
    Image.fromarray(foreground, "RGBA").save(TARGET / "preview.png", "PNG", optimize=False)

    definition = {
        "template_version": 2,
        "template_id": "pink_diamond",
        "display_name": "Pink Diamond",
        "sort_order": 0,
        "canvas": {"width": WIDTH, "height": HEIGHT, "resolution_status": "source-native"},
        "layers": {
            "background": "background.png",
            "player_mask": "player_mask.png",
            "foreground": "foreground.png",
        },
        "player_defaults": {
            "anchor_x": 187.0,
            "anchor_y": 405.0,
            "scale": 1.0,
            "rotation_degrees": 0.0,
            "flip_horizontal": False,
        },
        "text_fields": text_fields(),
        "extraction": {
            "source_count": 1,
            "composite_method": "user-supplied-transparent-frame",
            "single_source": True,
            "source_sha256": digest,
            "direct_visible_pixel_count": int(np.count_nonzero(alpha)) - (right - left) * (bottom - top),
            "transparent_player_pixel_count": int(np.count_nonzero(alpha == 0)),
            "source_patched_pixel_count": (right - left) * (bottom - top),
            "deterministic_composite_pixel_count": (right - left) * (bottom - top),
            "ovr_divider_source": "templates/diamond/foreground.png",
            "ovr_divider_source_rect": list(DIVIDER_BOX),
            "provenance_available": True,
            "authenticity_note": "The user-supplied transparent Pink Diamond frame is preserved, with the authentic neutral OVR divider transferred at identical coordinates from the maintained Diamond frame. No pixels were generated or recolored.",
        },
    }
    (TARGET / "template.json").write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")
    print(f"Installed {TARGET}")
    print(f"Visible frame pixels: {np.count_nonzero(alpha)}")
    print(f"Transparent player pixels: {np.count_nonzero(alpha == 0)}")


if __name__ == "__main__":
    main()
