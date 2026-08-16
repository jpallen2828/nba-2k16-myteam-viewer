"""Extract Bronze, Silver, Gold, and Amethyst built-in templates.

Only native source pixels, masks, transparent omission, deterministic OpenCV
inpainting, and audited source-coordinate texture clones are used. The original
source images are opened read-only and are not runtime dependencies.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from app.constants import APPLICATION_VERSION  # noqa: E402

WIDTH, HEIGHT = 325, 455
OUTPUT_ROOT = STUDIO_ROOT / "assets" / "built_in_templates"
LEGACY_TEMPLATE_ROOT = STUDIO_ROOT / "templates"

DEFAULT_SOURCES = {
    "amethyst": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-c50bd6c8-03d5-48bf-b108-710e93ac52fd.png"),
    "gold": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-f382e8a4-5606-4c28-ae13-c131a78e0443.png"),
    "silver": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-1e5de9ba-a742-433a-95f9-fa4814d6cb5e.png"),
    "bronze": Path(r"C:\Users\James\AppData\Local\Temp\codex-clipboard-0597b007-600b-4927-8713-ed01b38b9f24.png"),
}
EXPECTED_HASHES = {
    "amethyst": "DA0388E37A6E84E66F575D12766488B63FF948C2C4240B684F23D1748133BCA6",
    "gold": "3E482CFE5FF9FA5E0BC195DE412BA8E586DF2A2E6C0CF86AB6B35F92022A7D0F",
    "silver": "DB638FFA61810129EFD350FE121ED1A2242C5313EDD737F500985B66F0CFB9A1",
    "bronze": "21B337875EC36E42933FA0758E1B142207C870EB5AECEB68DCD3C9967926BEB5",
}
SOURCE_DESCRIPTIONS = {
    "amethyst": "1989 Michael Jordan, Chicago Bulls, 90 OVR Amethyst",
    "gold": "2014 Kawhi Leonard, San Antonio Spurs, 87 OVR Gold",
    "silver": "2014 Shane Battier, Miami Heat, 78 OVR Silver",
    "bronze": "1989 John Salley, Detroit Pistons, 69 OVR Bronze",
}
SOURCE_TEXT = {
    "amethyst": {"overall": "OVR 90", "position": "SG", "name": "'89 MICHAEL JORDAN"},
    "gold": {"overall": "OVR 87", "position": "SF", "name": "'14 KAWHI LEONARD"},
    "silver": {"overall": "OVR 78", "position": "SF", "name": "'14 SHANE BATTIER"},
    "bronze": {"overall": "OVR 69", "position": "PF", "name": "'89 JOHN SALLEY"},
}


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    kernel = np.ones((radius * 2 + 1, radius * 2 + 1), dtype=np.uint8)
    return cv2.dilate(mask.astype(np.uint8), kernel, iterations=1) > 0


def deterministic_inpaint(source: np.ndarray, output: np.ndarray, patch: np.ndarray, radius: int) -> None:
    bgr = cv2.cvtColor(source[:, :, :3], cv2.COLOR_RGB2BGR)
    cleaned = cv2.inpaint(bgr, patch.astype(np.uint8) * 255, radius, cv2.INPAINT_TELEA)
    output[patch, :3] = cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB)[patch]
    output[patch, 3] = source[patch, 3]


def interpolate_blank_panel(source: np.ndarray, output: np.ndarray, patch: np.ndarray) -> None:
    """Restore the simple tier-panel gradient from clean pixels on both sides."""
    for y in range(7, 53):
        xs = np.flatnonzero(patch[y])
        if not xs.size:
            continue
        left, right = int(xs.min()), int(xs.max())
        left_color = source[y, left - 1].astype(np.float32)
        right_color = source[y, right + 1].astype(np.float32)
        count = right - left + 1
        weights = np.linspace(1.0 / (count + 1), count / (count + 1), count, dtype=np.float32)[:, None]
        output[y, left : right + 1] = np.rint(left_color * (1.0 - weights) + right_color * weights).astype(np.uint8)


def polynomial_blank_panel(source: np.ndarray, output: np.ndarray, patch: np.ndarray) -> None:
    """Fit the smooth panel lighting only from nearby non-text source pixels."""
    yy, xx = np.indices((HEIGHT, WIDTH))
    panel = (xx >= 9) & (xx <= 46) & (yy >= 5) & (yy <= 52)
    donors = panel & ~dilate(patch, 1)
    donor_y, donor_x = np.nonzero(donors)
    x = (donor_x.astype(np.float64) - 27.5) / 19.0
    y = (donor_y.astype(np.float64) - 28.5) / 24.0
    design = np.column_stack((np.ones_like(x), x, y, x * y, x * x, y * y, y * y * y))
    target_y, target_x = np.nonzero(patch)
    tx = (target_x.astype(np.float64) - 27.5) / 19.0
    ty = (target_y.astype(np.float64) - 28.5) / 24.0
    target_design = np.column_stack((np.ones_like(tx), tx, ty, tx * ty, tx * tx, ty * ty, ty * ty * ty))
    for channel in range(3):
        coefficients, *_ = np.linalg.lstsq(design, source[donor_y, donor_x, channel].astype(np.float64), rcond=None)
        output[target_y, target_x, channel] = np.clip(np.rint(target_design @ coefficients), 0, 255).astype(np.uint8)
    output[target_y, target_x, 3] = source[target_y, target_x, 3]


def row_median_blank_panel(source: np.ndarray, output: np.ndarray, patch: np.ndarray) -> None:
    """Replace text from the panel's robust, vertically smoothed row colors."""
    expanded = dilate(patch, 1)
    colors = []
    for y in range(5, 53):
        clean_x = np.array([x for x in range(10, 47) if not expanded[y, x]], dtype=np.int16)
        if not clean_x.size:
            clean_x = np.array((10, 46), dtype=np.int16)
        colors.append(np.median(source[y, clean_x, :3], axis=0))
    color_strip = np.asarray(colors, dtype=np.float32).reshape((-1, 1, 3))
    color_strip = cv2.GaussianBlur(color_strip, (1, 9), 0).reshape((-1, 3))
    for y in range(5, 53):
        xs = np.flatnonzero(patch[y])
        if xs.size:
            output[y, xs, :3] = np.clip(np.rint(color_strip[y - 5]), 0, 255).astype(np.uint8)
            output[y, xs, 3] = source[y, xs, 3]


def mirrored_tile_patch(source: np.ndarray, output: np.ndarray, patch: np.ndarray, tile: tuple[int, int, int, int]) -> tuple[np.ndarray, np.ndarray]:
    left, top, right, bottom = tile
    tile_width, tile_height = right - left, bottom - top
    yy, xx = np.nonzero(patch)
    phase_x = np.mod(xx - left, tile_width * 2 - 2)
    phase_y = np.mod(yy - top, tile_height * 2 - 2)
    local_x = np.where(phase_x < tile_width, phase_x, tile_width * 2 - 2 - phase_x)
    local_y = np.where(phase_y < tile_height, phase_y, tile_height * 2 - 2 - phase_y)
    source_x = (left + local_x).astype(np.int16)
    source_y = (top + local_y).astype(np.int16)
    output[yy, xx] = source[source_y, source_x]
    return source_x, source_y


def bright_neutral(source: np.ndarray, box: tuple[int, int, int, int], threshold: int) -> np.ndarray:
    left, top, right, bottom = box
    region = source[top:bottom, left:right, :3].astype(np.int16)
    neutral = (np.max(region, axis=2) - np.min(region, axis=2)) < 55
    bright = np.min(region, axis=2) >= threshold
    result = np.zeros(source.shape[:2], dtype=bool)
    result[top:bottom, left:right] = neutral & bright
    return result


def text_layout(tier: str | None = None) -> dict:
    layout = {
        "overall": {
            "x": 10, "y": 24, "width": 36, "height": 29,
            "alignment": "center", "vertical_alignment": "center", "baseline": 49, "source_baseline": 23,
            "safe_inset_left": 2, "safe_inset_right": 2, "safe_inset_top": 2, "safe_inset_bottom": 1,
            "force_uppercase": True, "fit_mode": "scale_to_fit", "max_width": 32, "maximum_width": 32,
            "min_scale": 0.72, "preferred_tracking": 0.0, "minimum_tracking": -1.0,
            "text_style": "nba2k16_default", "expected_color": [244, 247, 246, 255], "clean": True,
            "label": {
                "x": 15, "y": 0, "width": 27, "height": 25, "alignment": "center",
                "baseline": 23, "source_baseline": 23, "maximum_width": 27, "min_scale": 1.0,
            },
            "notes": "Blank native OVR panel with dynamic source-extracted label and digits.",
        },
        "position": {
            "x": 13, "y": 416, "width": 26, "height": 35,
            "alignment": "center", "vertical_alignment": "center", "baseline": 438, "source_baseline": 16,
            "safe_inset_left": 1, "safe_inset_right": 1, "safe_inset_top": 3, "safe_inset_bottom": 3,
            "force_uppercase": True, "fit_mode": "scale_to_fit", "max_width": 24, "maximum_width": 24,
            "min_scale": 0.68, "preferred_tracking": 0.0, "minimum_tracking": -1.0,
            "text_style": "nba2k16_default", "expected_color": [242, 244, 239, 255], "clean": True,
            "notes": "Dynamic position centered inside the preserved circular badge.",
        },
        "name": {
            "x": 68, "y": 417, "width": 253, "height": 35,
            "alignment": "center", "vertical_alignment": "center", "baseline": 438, "source_baseline": 16,
            "safe_inset_left": 2, "safe_inset_right": 8, "safe_inset_top": 4, "safe_inset_bottom": 3,
            "force_uppercase": True, "fit_mode": "tighten_tracking_then_scale", "max_width": 243,
            "maximum_width": 243, "min_scale": 0.62, "preferred_tracking": 0.0, "minimum_tracking": -1.0,
            "text_style": "nba2k16_default", "expected_color": [244, 247, 246, 255], "clean": True,
            "notes": "Dynamic centered name kept outside the protected tier corner and position badge.",
        },
    }
    if tier in {"bronze", "silver", "gold"}:
        shadow = {"offset_x": 1, "offset_y": 1, "color": [0, 0, 0, 176]}
        layout["overall"]["shadow"] = shadow
        layout["overall"]["label"]["shadow"] = shadow
    return layout


def extraction_masks(source: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    yy, xx = np.indices((HEIGHT, WIDTH))
    # Select the authentic neutral-white glyph cores, then expand far enough to
    # include their antialiasing and dark outline. The organic glyph mask keeps
    # local inpainting from producing a rectangular deletion boundary.
    overall = bright_neutral(source, (13, 9, 43, 51), 140)
    overall = dilate(overall, 4) & (xx >= 9) & (xx <= 46) & (yy >= 5) & (yy <= 52)

    badge_inner = ((xx - 25) ** 2 + (yy - 432) ** 2) <= 13 ** 2
    position = bright_neutral(source, (12, 422, 39, 442), 140)
    position = dilate(position, 2) & badge_inner

    # Protect the permanent colored lower-left tier corner. Its diagonal ends
    # at x=82 on the bottom row in all four native sources.
    corner_image = Image.new("L", (WIDTH, HEIGHT), 0)
    ImageDraw.Draw(corner_image).polygon([(0, 403), (49, 403), (83, 454), (0, 454)], fill=255)
    corner = np.asarray(corner_image, dtype=np.uint8) > 0
    corner = dilate(corner, 1) & (yy >= 403) & (xx < 85)
    name = np.zeros((HEIGHT, WIDTH), dtype=bool)
    name[421:451, 68:321] = True
    name &= ~corner
    return overall, position, name, corner


def write_diagnostic_zoom(source: np.ndarray, cleaned: np.ndarray, destination: Path) -> None:
    # Exact nearest-neighbor enlargement for pixel-level visual review.
    crops = [(7, 0, 48, 61), (7, 410, 86, 455), (62, 414, 325, 455)]
    panels = []
    for image in (source, cleaned):
        row = []
        pil = Image.fromarray(image, "RGBA")
        for box in crops:
            crop = pil.crop(box)
            crop.thumbnail((526, 180), Image.Resampling.NEAREST)
            row.append(crop)
        width = sum(item.width for item in row) + 12 * (len(row) - 1)
        line = Image.new("RGBA", (width, max(item.height for item in row)), (15, 18, 24, 255))
        cursor = 0
        for item in row:
            line.alpha_composite(item, (cursor, 0)); cursor += item.width + 12
        panels.append(line)
    sheet = Image.new("RGBA", (max(item.width for item in panels), sum(item.height for item in panels) + 12), (15, 18, 24, 255))
    sheet.alpha_composite(panels[0], (0, 0)); sheet.alpha_composite(panels[1], (0, panels[0].height + 12))
    sheet.resize((sheet.width * 2, sheet.height * 2), Image.Resampling.NEAREST).save(destination, optimize=False)


def extract_tier(tier: str, source_path: Path, output_root: Path) -> None:
    digest = sha256(source_path.read_bytes()).hexdigest().upper()
    if source_path == DEFAULT_SOURCES[tier] and digest != EXPECTED_HASHES[tier]:
        raise RuntimeError(f"{tier} source hash changed: {digest}")
    with Image.open(source_path) as opened:
        if opened.size != (WIDTH, HEIGHT):
            raise RuntimeError(f"{tier} source is {opened.size}; expected {(WIDTH, HEIGHT)}")
        source_image = opened.convert("RGBA")
    source = np.asarray(source_image, dtype=np.uint8)
    cleaned = source.copy()
    overall, position, name, corner = extraction_masks(source)
    row_median_blank_panel(source, cleaned, overall)
    deterministic_inpaint(source, cleaned, position, 3)
    donor_x, donor_y = mirrored_tile_patch(source, cleaned, name, (310, 421, 322, 451))

    yy, xx = np.indices((HEIGHT, WIDTH))
    opening = (xx >= 49) & (yy < 404)
    visible = ~opening
    foreground = cleaned.copy()
    foreground[opening] = (0, 0, 0, 0)
    background = np.zeros_like(source)
    player_mask = opening.astype(np.uint8) * 255
    preview = Image.alpha_composite(Image.fromarray(background, "RGBA"), Image.fromarray(foreground, "RGBA"))

    destination = output_root / tier
    diagnostics = destination / "diagnostics"
    diagnostics.mkdir(parents=True, exist_ok=True)
    Image.fromarray(background, "RGBA").save(destination / "background.png", optimize=False)
    Image.fromarray(foreground, "RGBA").save(destination / "foreground.png", optimize=False)
    Image.fromarray(player_mask, "L").save(destination / "player_mask.png", optimize=False)
    preview.save(destination / "preview.png", optimize=False)
    Image.fromarray(opening.astype(np.uint8) * 255, "L").save(diagnostics / "unresolved.png", optimize=False)

    changed = overall | position | name
    provenance = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    provenance[visible & ~changed] = (55, 170, 245, 255)
    provenance[name] = (255, 164, 50, 255)
    provenance[overall | position] = (255, 220, 70, 255)
    provenance[opening] = (226, 58, 82, 160)
    Image.fromarray(provenance, "RGBA").save(diagnostics / "provenance.png", optimize=False)
    write_diagnostic_zoom(source, cleaned, diagnostics / "cleanup_zoom.png")

    definition = {
        "template_version": 2,
        "template_id": tier,
        "display_name": tier.title(),
        "sort_order": ["pink_diamond", "diamond", "amethyst", "gold", "silver", "bronze"].index(tier),
        "canvas": {"width": WIDTH, "height": HEIGHT, "resolution_status": "source-native"},
        "layers": {"background": "background.png", "player_mask": "player_mask.png", "foreground": "foreground.png"},
        "player_defaults": {"anchor_x": 187.0, "anchor_y": 405.0, "scale": 1.0, "rotation_degrees": 0.0, "flip_horizontal": False},
        "text_fields": text_layout(tier),
        "extraction": {
            "source_count": 1, "single_source": True, "source_filename": source_path.name,
            "source_description": SOURCE_DESCRIPTIONS[tier], "source_sha256": digest,
            "method": "transparent-variable-field-with-source-pixel-text-cleanup",
            "source_patched_pixel_count": int(np.count_nonzero(name)),
            "deterministic_composite_pixel_count": int(np.count_nonzero(overall | position)),
            "transparent_center_pixel_count": int(np.count_nonzero(opening)),
            "provenance_available": True,
            "authenticity_note": "Visible frame pixels are direct or deterministically cleaned from the attached native source. Card-specific center art is transparent, not reconstructed.",
        },
    }
    (destination / "template.json").write_text(json.dumps(definition, indent=2) + "\n", encoding="utf-8")

    report = {
        "template_id": tier, "display_name": tier.title(), "application_version": APPLICATION_VERSION,
        "source": source_path.name, "source_description": SOURCE_DESCRIPTIONS[tier], "source_sha256": digest,
        "dimensions": {"width": WIDTH, "height": HEIGHT}, "source_modified": False, "source_resampled": False,
        "preserved": ["tier-colored left rail", "native bevels and outlines", "blank OVR panel structure", "circular position container", "tier-colored lower-left corner", "bottom nameplate and separator"],
        "removed": ["all central player/team/background artwork", "team logo and lettering", "medal or Historic Players graphic", SOURCE_TEXT[tier]["overall"], SOURCE_TEXT[tier]["position"], SOURCE_TEXT[tier]["name"]],
        "transparent_center": True, "blank_dynamic_text_regions": ["overall", "position", "name"],
        "direct_visible_pixel_count": int(np.count_nonzero(visible & ~changed)),
        "source_cloned_pixel_count": int(np.count_nonzero(name)),
        "deterministic_source_composite_pixel_count": int(np.count_nonzero(overall | position)),
        "unresolved": ["Artwork hidden behind the source-specific center cannot be recovered from one card and is intentionally transparent."],
        "name_clone_source_rect": [310, 421, 322, 451],
        "name_clone_donor_coordinate_count": int(len(donor_x)),
        "quality_statement": "Native frame extraction with intentionally transparent card-specific center; no image generation, generative fill, resize, or hidden-art reconstruction.",
    }
    (diagnostics / "extraction_report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def install_existing_template(template_id: str, sort_order: int, output_root: Path) -> None:
    source = LEGACY_TEMPLATE_ROOT / template_id
    destination = output_root / template_id
    destination.mkdir(parents=True, exist_ok=True)
    for filename in ("background.png", "foreground.png", "player_mask.png", "preview.png", "template.json"):
        shutil.copyfile(source / filename, destination / filename)
    data = json.loads((destination / "template.json").read_text(encoding="utf-8"))
    data["sort_order"] = sort_order
    (destination / "template.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=OUTPUT_ROOT)
    for tier, default in DEFAULT_SOURCES.items():
        parser.add_argument(f"--{tier}-source", type=Path, default=default)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_root = args.output_root.resolve()
    for tier in ("bronze", "silver", "gold", "amethyst"):
        extract_tier(tier, getattr(args, f"{tier}_source").resolve(), output_root)
        print(f"Extracted {tier}: {output_root / tier}")
    install_existing_template("diamond", 1, output_root)
    install_existing_template("pink_diamond", 0, output_root)
    print(f"Installed Diamond runtime layers: {output_root / 'diamond'}")
    print(f"Installed Pink Diamond runtime layers: {output_root / 'pink_diamond'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
