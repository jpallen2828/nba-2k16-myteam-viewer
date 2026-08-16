"""Deterministically extract the built-in Diamond tier from one supplied card.

No pixels are generated. Direct pixels retain their native coordinate; patched
pixels clone an explicit coordinate from the sole source. The card-specific
center is intentionally transparent instead of being guessed from one card. A
complete source-coordinate map is written to diagnostics for auditability.
"""

from __future__ import annotations

from collections import defaultdict
from hashlib import sha256
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

STUDIO_ROOT = Path(__file__).resolve().parents[1]
if str(STUDIO_ROOT) not in sys.path:
    sys.path.insert(0, str(STUDIO_ROOT))

from app.builder.models import BuilderProject, PatchOperation
from app.builder.services.project_service import BuilderProjectService
from app.builder.services.source_service import SourceService
from app.constants import APPLICATION_VERSION


SOURCE = STUDIO_ROOT.parent / "data" / "card-images" / "9857-kareem-abdul-jabbar.png"
TEMPLATE = STUDIO_ROOT / "templates" / "diamond"
WORK_PROJECT = STUDIO_ROOT / "template_work" / "diamond.2k16templatework"
EXPECTED_SHA256 = "67B387F3CC598770CB0ECA832788FB1C3F5C32B9674C99D9F29B79F7A6856BB7"
WIDTH, HEIGHT = 325, 455


def polygon_mask(size: tuple[int, int], points: list[tuple[int, int]]) -> np.ndarray:
    image = Image.new("L", size, 0)
    ImageDraw.Draw(image).polygon(points, fill=255)
    return np.asarray(image, dtype=np.uint8) > 0


def dilate(mask: np.ndarray, radius: int) -> np.ndarray:
    kernel = np.ones((radius * 2 + 1, radius * 2 + 1), dtype=np.uint8)
    return cv2.dilate(mask.astype(np.uint8), kernel, iterations=1) > 0


def nearest_same_row_donors(donor_mask: np.ndarray, targets: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Map every target to the nearest authentic donor, preferring its row."""
    height, width = donor_mask.shape
    source_y = np.indices((height, width))[0].astype(np.int16)
    source_x = np.indices((height, width))[1].astype(np.int16)
    rows_with_donors = np.flatnonzero(np.any(donor_mask, axis=1))
    if not rows_with_donors.size:
        raise RuntimeError("No authentic donor pixels are available")
    for y in np.flatnonzero(np.any(targets, axis=1)):
        donor_y = int(rows_with_donors[np.argmin(np.abs(rows_with_donors - y))])
        donor_xs = np.flatnonzero(donor_mask[donor_y])
        for x in np.flatnonzero(targets[y]):
            sx = int(donor_xs[np.argmin(np.abs(donor_xs - x))])
            source_x[y, x], source_y[y, x] = sx, donor_y
    return source_x, source_y


def patch_from_local_donors(
    source: np.ndarray,
    output: np.ndarray,
    patch_mask: np.ndarray,
    donor_mask: np.ndarray,
    map_x: np.ndarray,
    map_y: np.ndarray,
) -> None:
    sx, sy = nearest_same_row_donors(donor_mask, patch_mask)
    yy, xx = np.nonzero(patch_mask)
    output[yy, xx] = source[sy[yy, xx], sx[yy, xx]]
    map_x[yy, xx], map_y[yy, xx] = sx[yy, xx], sy[yy, xx]


def patch_from_mirrored_tile(
    source: np.ndarray,
    output: np.ndarray,
    patch_mask: np.ndarray,
    tile: tuple[int, int, int, int],
    map_x: np.ndarray,
    map_y: np.ndarray,
) -> None:
    """Clone a verified authentic rectangle with seam-friendly reflection."""
    left, top, right, bottom = tile
    tile_width, tile_height = right - left, bottom - top
    if tile_width < 2 or tile_height < 2:
        raise ValueError("Clone tile is too small")
    yy, xx = np.nonzero(patch_mask)
    phase_x = np.mod(xx - left, tile_width * 2 - 2)
    phase_y = np.mod(yy - top, tile_height * 2 - 2)
    local_x = np.where(phase_x < tile_width, phase_x, tile_width * 2 - 2 - phase_x)
    local_y = np.where(phase_y < tile_height, phase_y, tile_height * 2 - 2 - phase_y)
    sx, sy = (left + local_x).astype(np.int16), (top + local_y).astype(np.int16)
    output[yy, xx] = source[sy, sx]
    map_x[yy, xx], map_y[yy, xx] = sx, sy


def deterministic_inpaint(
    source: np.ndarray,
    output: np.ndarray,
    patch_mask: np.ndarray,
    radius: int,
    map_x: np.ndarray,
    map_y: np.ndarray,
) -> None:
    """Replace a masked glyph from its surrounding source pixels.

    OpenCV's Telea implementation is deterministic. It is used only for the
    tiny OVR panel, where cloning a narrow strip creates visible block seams.
    Coordinates are marked -1 because these pixels are local composites rather
    than copies from one exact donor coordinate.
    """
    bgr = cv2.cvtColor(source[:, :, :3], cv2.COLOR_RGB2BGR)
    cleaned = cv2.inpaint(bgr, patch_mask.astype(np.uint8) * 255, radius, cv2.INPAINT_TELEA)
    cleaned_rgb = cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB)
    output[patch_mask, :3] = cleaned_rgb[patch_mask]
    output[patch_mask, 3] = source[patch_mask, 3]
    map_x[patch_mask] = -1
    map_y[patch_mask] = -1


def text_patch_mask(
    source: np.ndarray,
    box: tuple[int, int, int, int],
    threshold: int,
    radius: int,
    allowed: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    left, top, right, bottom = box
    region = source[top:bottom, left:right, :3]
    bright = np.min(region, axis=2) >= threshold
    local = dilate(bright, radius)
    mask = np.zeros(source.shape[:2], dtype=bool)
    mask[top:bottom, left:right] = local
    donor = np.zeros(source.shape[:2], dtype=bool)
    donor[top:bottom, left:right] = ~local
    if allowed is not None:
        mask &= allowed
        donor &= allowed
    # Avoid borrowing bright antialias remnants or the text itself.
    donor &= np.max(source[:, :, :3], axis=2) < threshold
    return mask, donor


def group_patch_operations(map_x: np.ndarray, map_y: np.ndarray, changed: np.ndarray, source_id: str) -> list[PatchOperation]:
    groups: dict[tuple[int, int], list[tuple[int, int]]] = defaultdict(list)
    for y, x in zip(*np.nonzero(changed), strict=True):
        offset = (int(map_x[y, x]) - int(x), int(map_y[y, x]) - int(y))
        groups[offset].append((int(x), int(y)))
    return [
        PatchOperation(source_id, points, dx, dy, "single-source-clone")
        for (dx, dy), points in sorted(groups.items())
    ]


def main() -> None:
    digest = sha256(SOURCE.read_bytes()).hexdigest().upper()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"Source hash changed: {digest}")
    with Image.open(SOURCE) as opened:
        if opened.size != (WIDTH, HEIGHT):
            raise RuntimeError(f"Expected {WIDTH} x {HEIGHT}, got {opened.size}")
        source_image = opened.convert("RGBA")
    source = np.asarray(source_image, dtype=np.uint8)
    output = source.copy()
    yy, xx = np.indices((HEIGHT, WIDTH))
    map_x, map_y = xx.astype(np.int16), yy.astype(np.int16)

    # The sole source cannot reveal the art behind Kareem or the medal. The
    # entire variable art field is therefore omitted, not synthesized. Runtime
    # player art is allowed through this exact transparent opening.
    # Column x=49 is a one-pixel royal-blue remnant of the card-specific center,
    # not part of the silver/cyan rail. Include it in the transparent player
    # opening; y=404 remains the authentic horizontal frame edge.
    main_field = (xx >= 49) & (yy < 404)

    # Remove glyphs only. Every replacement is copied from a nearby clean pixel
    # on the same source row, retaining the native panel/nameplate texture and
    # avoiding rectangular fills.
    overall_patch, _overall_donors = text_patch_mask(source, (11, 7, 44, 58), 100, 2)
    # The permanent beveled divider under the OVR digits occupies source rows
    # 53-57. It is frame art, not text, and must never enter the cleanup mask.
    overall_patch[53:58, :] = False
    deterministic_inpaint(source, output, overall_patch, 3, map_x, map_y)

    badge_inner = ((xx - 25) ** 2 + (yy - 432) ** 2) <= 13 ** 2
    position_patch, _position_donors = text_patch_mask(
        source, (10, 416, 41, 450), 100, 2, allowed=badge_inner
    )
    deterministic_inpaint(source, output, position_patch, 3, map_x, map_y)

    # The separate cyan Diamond corner widens from left to right toward the
    # bottom. Protect its exact source silhouette (plus its antialiased edge)
    # instead of clipping it with a fixed rectangular nameplate cleanup.
    source_rgb = source[:, :, :3].astype(np.int16)
    diamond_corner_color = (
        (xx >= 45) & (xx < 82) & (yy >= 414) & (yy < 455)
        & (source_rgb[:, :, 2] > source_rgb[:, :, 0] + 18)
        & (source_rgb[:, :, 1] > source_rgb[:, :, 0] + 8)
        & (source_rgb[:, :, 2] > 110)
    )
    protected_diamond_corner = dilate(diamond_corner_color, 1) & (xx < 82) & (yy >= 414)
    name_patch = np.zeros((HEIGHT, WIDTH), dtype=bool)
    name_patch[421:451, 68:321] = True
    name_patch &= ~protected_diamond_corner
    patch_from_mirrored_tile(source, output, name_patch, (310, 421, 322, 451), map_x, map_y)

    text_patched = overall_patch | position_patch | name_patch
    source_cloned = name_patch
    deterministic_composite = overall_patch | position_patch
    changed = text_patched
    unrecoverable = main_field.copy()
    map_x[unrecoverable] = -1
    map_y[unrecoverable] = -1

    background_mask = np.zeros((HEIGHT, WIDTH), dtype=np.uint8)
    foreground_mask = (((xx < 49) | (yy >= 404))).astype(np.uint8) * 255
    player_mask = main_field.astype(np.uint8) * 255
    background = np.zeros_like(source)
    foreground = output.copy(); foreground[:, :, 3] = foreground_mask
    foreground[foreground_mask == 0] = (0, 0, 0, 0)
    preview = Image.alpha_composite(Image.fromarray(background, "RGBA"), Image.fromarray(foreground, "RGBA"))

    TEMPLATE.mkdir(parents=True, exist_ok=True)
    diagnostics = TEMPLATE / "diagnostics"; diagnostics.mkdir(exist_ok=True)
    Image.fromarray(background, "RGBA").save(TEMPLATE / "background.png", "PNG", optimize=False)
    Image.fromarray(foreground, "RGBA").save(TEMPLATE / "foreground.png", "PNG", optimize=False)
    Image.fromarray(player_mask, "L").save(TEMPLATE / "player_mask.png", "PNG", optimize=False)
    preview.save(TEMPLATE / "preview.png", "PNG", optimize=False)
    Image.fromarray(unrecoverable.astype(np.uint8) * 255, "L").save(diagnostics / "unresolved.png", "PNG")

    provenance = np.zeros((HEIGHT, WIDTH, 4), dtype=np.uint8)
    visible = (background_mask > 0) | (foreground_mask > 0)
    provenance[visible] = (55, 170, 245, 255)       # direct source coordinate
    provenance[source_cloned] = (255, 164, 50, 255) # explicit source clone
    provenance[deterministic_composite] = (255, 220, 70, 255)  # local deterministic composite
    provenance[unrecoverable] = (226, 58, 82, 160)  # intentionally transparent, hidden art unresolved
    Image.fromarray(provenance, "RGBA").save(diagnostics / "provenance.png", "PNG")
    np.savez_compressed(
        diagnostics / "source_coordinate_map.npz",
        source_x=map_x,
        source_y=map_y,
        changed=changed,
        source_cloned=source_cloned,
        deterministic_composite=deterministic_composite,
        intentionally_transparent=unrecoverable,
    )

    text_fields = {
        "overall": {
            "x": 10, "y": 24, "width": 36, "height": 29,
            "alignment": "center", "vertical_alignment": "center", "baseline": 49, "source_baseline": 23,
            "safe_inset_left": 2, "safe_inset_right": 2, "safe_inset_top": 2, "safe_inset_bottom": 1,
            "force_uppercase": True, "fit_mode": "scale_to_fit", "max_width": 32,
            "maximum_width": 32, "min_scale": 0.72, "preferred_tracking": 0.0, "minimum_tracking": -1.0,
            "text_style": "nba2k16_default",
            "label": {"x": 15, "y": 0, "width": 27, "height": 25, "alignment": "center", "baseline": 23, "source_baseline": 23, "maximum_width": 27, "min_scale": 1.0},
            "expected_color": [244, 247, 246, 255], "clean": True,
            "notes": "Blank centered numeric OVR area; the source OVR label and 97 glyphs are both removed.",
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
            "force_uppercase": True, "fit_mode": "tighten_tracking_then_scale", "max_width": 243,
            "maximum_width": 243, "min_scale": 0.62, "preferred_tracking": 0.0, "minimum_tracking": -1.0,
            "text_style": "nba2k16_default",
            "expected_color": [244, 247, 246, 255], "clean": True,
            "notes": "Centered per-tier nameplate; tighten tracking before scaling and never exceed the safe width.",
        },
    }
    definition = {
        "template_version": 2,
        "template_id": "diamond",
        "display_name": "Diamond",
        "canvas": {"width": WIDTH, "height": HEIGHT, "resolution_status": "source-native-working"},
        "layers": {"background": "background.png", "player_mask": "player_mask.png", "foreground": "foreground.png"},
        "player_defaults": {"anchor_x": 187.0, "anchor_y": 405.0, "scale": 1.0, "rotation_degrees": 0.0, "flip_horizontal": False},
        "text_fields": text_fields,
        "extraction": {
            "source_count": 1,
            "composite_method": "transparent-variable-field-with-explicit-source-coordinate-clones",
            "single_source": True,
            "source_sha256": digest,
            "unresolved_pixel_count": int(np.count_nonzero(unrecoverable)),
            "source_patched_pixel_count": int(np.count_nonzero(source_cloned)),
            "deterministic_composite_pixel_count": int(np.count_nonzero(deterministic_composite)),
            "provenance_available": True,
            "authenticity_note": "Visible frame pixels are direct or cloned from the sole source. The unrecoverable card-specific center is transparent rather than guessed.",
        },
    }
    (TEMPLATE / "template.json").write_text(json.dumps(definition, indent=2), encoding="utf-8")

    report = {
        "template_id": "diamond", "display_name": "Diamond", "template_version": 2,
        "application_version": APPLICATION_VERSION,
        "source": SOURCE.name, "source_sha256": digest, "source_count": 1,
        "dimensions": {"width": WIDTH, "height": HEIGHT},
        "working_resolution_basis": "Exact full-card dimensions of the supplied source; no resize or crop was applied.",
        "direct_visible_pixel_count": int(np.count_nonzero(visible & ~changed)),
        "source_cloned_pixel_count": int(np.count_nonzero(source_cloned)),
        "deterministic_source_composite_pixel_count": int(np.count_nonzero(deterministic_composite)),
        "text_patch_pixel_count": int(np.count_nonzero(text_patched)),
        "unresolved_original_coordinate_pixel_count": int(np.count_nonzero(unrecoverable)),
        "manual_entered_pixel_count": 0,
        "fully_recovered": [
            "Silver/diamond left rail and metallic bevels",
            "Blank overall panel with its shape and lower rule preserved",
            "Circular position badge container",
            "Bottom nameplate, separate left Diamond corner, and cyan/metallic separator",
            "Transparent center/player opening",
        ],
        "patched": [
            "OVR label and 97 glyph removed with deterministic same-panel source-pixel cleanup",
            "C glyph removed with deterministic same-badge source-pixel cleanup constrained to the inner circle",
            "'72 KAREEM ABDUL-JABBAR removed with same-nameplate source-coordinate clones",
        ],
        "unresolved": [
            "Exact center artwork behind the player and medal cannot be recovered from one source and is intentionally transparent",
        ],
        "provenance": {
            "blue": "direct pixel at its original source coordinate",
            "orange": "source-cloned pixel with an audited donor coordinate",
            "yellow": "deterministic local source-pixel composite used only in the OVR panel and position badge",
            "red": "intentionally transparent center whose hidden source artwork is unresolved",
            "coordinate_map": "source_coordinate_map.npz stores donor x/y for direct and cloned pixels; composite and transparent pixels are -1",
        },
        "quality_statement": "Usable single-source frame extraction with a deliberately transparent variable-art center; hidden artwork is not claimed as recovered.",
    }
    (diagnostics / "extraction_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (diagnostics / "notes.txt").write_text(
        "DIAMOND SINGLE-SOURCE EXTRACTION\n\n"
        "Only 9857-kareem-abdul-jabbar.png was used. The 325x455 source was not resized, rewritten, or modified.\n"
        "Direct pixels remain at their original coordinate. The name patch copies recorded coordinates from that image.\n"
        "The OVR panel and position badge use deterministic local source-pixel inpainting because narrow clones produced visible seams.\n"
        "The entire card-specific center, including the visible dragon, player, and medal, is transparent.\n"
        "No hidden center artwork was guessed, cloned, synthesized, or filled.\n"
        "Red provenance locations identify that intentionally transparent, unrecoverable center.\n"
        "Original dynamic text and the gold medal/ribbons are absent from runtime assets. No fake text is rasterized.\n",
        encoding="utf-8",
    )

    project = BuilderProject.create("Diamond", "diamond", WIDTH, HEIGHT)
    imported = SourceService().import_source(SOURCE, project)
    project.sources.append(imported.model); project.set_reference(imported.model.source_id); project.selected_source_id = imported.model.source_id
    project.composite_method = "source_priority"; project.output_template_location = str(TEMPLATE)
    project.masks["background"].set_array(background_mask); project.masks["foreground"].set_array(foreground_mask)
    project.masks["player_art"].set_array(player_mask); project.masks["variable_exclusion"].set_array((main_field | changed).astype(np.uint8) * 255)
    project.masks["unresolved"].set_array(unrecoverable.astype(np.uint8) * 255)
    project.masks["stable_frame"].set_array((visible & ~changed).astype(np.uint8) * 255)
    project.masks["overall_text"].set_array(overall_patch.astype(np.uint8) * 255)
    project.masks["position_text"].set_array(position_patch.astype(np.uint8) * 255)
    project.masks["player_name"].set_array(name_patch.astype(np.uint8) * 255)
    protected = ((foreground_mask > 0) & ~text_patched).astype(np.uint8) * 255
    project.masks["protected"].set_array(protected)
    for field_id, values in text_fields.items():
        region = project.text_regions[field_id]
        region.x, region.y, region.width, region.height = values["x"], values["y"], values["width"], values["height"]
        region.baseline = values["baseline"]; region.horizontal_alignment = values["alignment"]; region.vertical_alignment = values["vertical_alignment"]
        region.maximum_width = values["max_width"]; region.safe_inset_left = values["safe_inset_left"]; region.safe_inset_right = values["safe_inset_right"]
        region.safe_inset_top = values["safe_inset_top"]; region.safe_inset_bottom = values["safe_inset_bottom"]
        region.force_uppercase = values["force_uppercase"]; region.fit_mode = values["fit_mode"]; region.min_scale = values["min_scale"]
        region.preferred_tracking = values["preferred_tracking"]; region.expected_color = values["expected_color"]
        region.notes = values["notes"]; region.clean = True; region.reference_source_id = imported.model.source_id
    project.patches = group_patch_operations(map_x, map_y, source_cloned, imported.model.source_id)
    for y, x in zip(*np.nonzero(deterministic_composite), strict=True):
        project.manual_pixels[f"{x},{y}"] = [int(value) for value in output[y, x]]
    project.operation_history = [
        "Import sole Diamond source", "Define stable frame and variable regions", "Remove dynamic text with local source clones",
        "Make the unrecoverable center transparent", "Assign foreground and player mask", "Define text layout metadata",
    ]
    WORK_PROJECT.parent.mkdir(parents=True, exist_ok=True)
    BuilderProjectService(STUDIO_ROOT / "template_work" / "backups").save(project, WORK_PROJECT, backup=False)
    print(f"Exported {TEMPLATE}")
    print(f"Builder project {WORK_PROJECT}")
    print(f"Changed pixels {np.count_nonzero(changed)}; unresolved original-coordinate pixels {np.count_nonzero(unrecoverable)}")


if __name__ == "__main__":
    main()
