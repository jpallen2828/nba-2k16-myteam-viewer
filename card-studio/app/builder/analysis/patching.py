"""Apply source patches and manual pixels while preserving provenance."""

from __future__ import annotations

import numpy as np
from PIL import Image

from app.builder.models import PatchOperation


PROVENANCE_COMPOSITE = -1
PROVENANCE_MANUAL = -2
PROVENANCE_UNRESOLVED = -3


def apply_edits(
    candidate: Image.Image,
    sources: dict[str, Image.Image],
    source_indices: dict[str, int],
    patches: list[PatchOperation],
    manual_pixels: dict[str, list[int]],
    base_provenance: np.ndarray | None = None,
) -> tuple[Image.Image, np.ndarray]:
    result = np.asarray(candidate.convert("RGBA"), dtype=np.uint8).copy()
    height, width = result.shape[:2]
    provenance = (
        np.asarray(base_provenance, dtype=np.int16).copy()
        if base_provenance is not None
        else np.full((height, width), PROVENANCE_COMPOSITE, dtype=np.int16)
    )
    for patch in patches:
        source_image = sources.get(patch.source_id)
        if source_image is None:
            continue
        source = np.asarray(source_image.convert("RGBA"), dtype=np.uint8)
        for x, y in patch.points:
            sx, sy = x + patch.source_offset_x, y + patch.source_offset_y
            if 0 <= x < width and 0 <= y < height and 0 <= sx < width and 0 <= sy < height:
                result[y, x] = source[sy, sx]
                provenance[y, x] = source_indices.get(patch.source_id, PROVENANCE_COMPOSITE)
    for coordinate, rgba in manual_pixels.items():
        try:
            x, y = (int(value) for value in coordinate.split(",", 1))
        except (TypeError, ValueError):
            continue
        if 0 <= x < width and 0 <= y < height and len(rgba) == 4:
            result[y, x] = np.asarray(rgba, dtype=np.uint8)
            provenance[y, x] = PROVENANCE_MANUAL
    return Image.fromarray(result, "RGBA"), provenance


def provenance_view(provenance: np.ndarray, source_count: int) -> Image.Image:
    palette = np.asarray(
        ((64, 170, 255), (255, 157, 66), (105, 214, 132), (200, 112, 255), (255, 220, 80), (80, 220, 210)),
        dtype=np.uint8,
    )
    height, width = provenance.shape
    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    rgba[provenance == PROVENANCE_COMPOSITE, :3] = (115, 125, 145)
    rgba[provenance == PROVENANCE_MANUAL, :3] = (255, 70, 90)
    rgba[provenance == PROVENANCE_UNRESOLVED, :3] = (10, 10, 10)
    for index in range(source_count):
        rgba[provenance == index, :3] = palette[index % len(palette)]
    return Image.fromarray(rgba, "RGBA")
