"""Non-destructive crop, perspective, and alignment transforms."""

from __future__ import annotations

import math

import cv2
import numpy as np
from PIL import Image

from app.builder.models import SourceTransform


class NormalizationError(ValueError):
    """Raised when a source transform cannot form a valid card rectangle."""


def _rgba(image: Image.Image) -> np.ndarray:
    return np.asarray(image.convert("RGBA"), dtype=np.uint8)


def validate_corners(corners: list[tuple[float, float]]) -> None:
    if len(corners) != 4:
        raise NormalizationError("Exactly four corners are required")
    points = np.asarray(corners, dtype=np.float32)
    if not np.isfinite(points).all():
        raise NormalizationError("Corner coordinates must be finite")
    contour = points.reshape((-1, 1, 2))
    if not cv2.isContourConvex(contour.astype(np.int32)) or abs(cv2.contourArea(contour)) < 1:
        raise NormalizationError("Corners must form a non-degenerate convex quadrilateral")


def normalize_source(
    source: Image.Image,
    output_size: tuple[int, int],
    transform: SourceTransform | None = None,
) -> Image.Image:
    """Return a transformed copy; never mutates or rewrites *source*."""
    transform = transform or SourceTransform()
    width, height = (int(output_size[0]), int(output_size[1]))
    if width <= 0 or height <= 0:
        raise NormalizationError("Output dimensions must be positive")
    untouched = (
        source.size == (width, height)
        and transform.crop_rect is None
        and transform.corners is None
        and transform.translate_x == 0
        and transform.translate_y == 0
        and transform.scale == 1
        and transform.rotation_degrees == 0
    )
    if untouched:
        return source.convert("RGBA").copy()

    array = _rgba(source)
    if transform.corners:
        validate_corners(transform.corners)
        source_points = np.asarray(transform.corners, dtype=np.float32)
        destination = np.asarray(((0, 0), (width - 1, 0), (width - 1, height - 1), (0, height - 1)), dtype=np.float32)
        matrix = cv2.getPerspectiveTransform(source_points, destination)
        normalized = cv2.warpPerspective(
            array,
            matrix,
            (width, height),
            flags=cv2.INTER_NEAREST,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )
    elif transform.crop_rect:
        left, top, right, bottom = transform.crop_rect
        if right <= left or bottom <= top:
            raise NormalizationError("Crop rectangle must have positive width and height")
        if left < 0 or top < 0 or right > source.width or bottom > source.height:
            raise NormalizationError("Crop rectangle is outside the source image")
        cropped = source.convert("RGBA").crop((round(left), round(top), round(right), round(bottom)))
        resampling = Image.Resampling.NEAREST if cropped.size != (width, height) else Image.Resampling.NEAREST
        normalized = np.asarray(cropped.resize((width, height), resampling), dtype=np.uint8)
    else:
        normalized = cv2.resize(array, (width, height), interpolation=cv2.INTER_NEAREST)

    if (
        abs(transform.translate_x) > 1e-9
        or abs(transform.translate_y) > 1e-9
        or abs(transform.scale - 1) > 1e-9
        or abs(transform.rotation_degrees) > 1e-9
    ):
        center = ((width - 1) / 2, (height - 1) / 2)
        matrix = cv2.getRotationMatrix2D(center, -transform.rotation_degrees, transform.scale)
        tx = transform.translate_x if transform.subpixel else round(transform.translate_x)
        ty = transform.translate_y if transform.subpixel else round(transform.translate_y)
        matrix[0, 2] += tx
        matrix[1, 2] += ty
        interpolation = cv2.INTER_LINEAR if transform.subpixel or not math.isclose(transform.scale, 1) or transform.rotation_degrees else cv2.INTER_NEAREST
        normalized = cv2.warpAffine(
            normalized,
            matrix,
            (width, height),
            flags=interpolation,
            borderMode=cv2.BORDER_CONSTANT,
            borderValue=(0, 0, 0, 0),
        )
    return Image.fromarray(normalized.astype(np.uint8), "RGBA")
