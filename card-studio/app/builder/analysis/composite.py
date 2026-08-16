"""Deterministic candidate composites and measurable diagnostic maps."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from PIL import Image


COMPOSITE_METHODS = (
    "median",
    "trimmed_mean",
    "exact_rgba_mode",
    "rgb_mode_alpha",
    "lowest_variance_source",
    "source_priority",
    "consensus_threshold",
)


@dataclass(frozen=True, slots=True)
class CompositeResult:
    image: Image.Image
    variance: np.ndarray
    alpha_variance: np.ndarray
    maximum_difference: np.ndarray
    consensus: np.ndarray
    agreement_count: np.ndarray
    provenance: np.ndarray
    confidence: np.ndarray


def _mode_rows(values: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return deterministic mode, count, and first-source index for N,H,W,C."""
    count, height, width, channels = values.shape
    encoded = np.zeros((count, height, width), dtype=np.uint32)
    for channel in range(channels):
        encoded |= values[:, :, :, channel].astype(np.uint32) << (channel * 8)
    best_count = np.zeros((height, width), dtype=np.uint16)
    provenance = np.zeros((height, width), dtype=np.int16)
    # Source loop only; all card pixels are evaluated in vectorized arrays.
    # Strictly-greater replacement preserves earliest-source tie breaking.
    for source_index in range(count):
        frequency = np.sum(encoded == encoded[source_index][None], axis=0, dtype=np.uint16)
        replace = frequency > best_count
        best_count[replace] = frequency[replace]
        provenance[replace] = source_index
    yy, xx = np.indices((height, width))
    chosen = values[provenance, yy, xx]
    return chosen, best_count, provenance


def _composite_array(stack: np.ndarray, method: str, trim_fraction: float, consensus_threshold: float) -> tuple[np.ndarray, np.ndarray]:
    count, height, width, _ = stack.shape
    if method == "median":
        result = np.rint(np.median(stack, axis=0)).astype(np.uint8)
        distances = np.abs(stack.astype(np.int16) - result[None].astype(np.int16)).sum(axis=3)
        provenance = np.argmin(distances, axis=0).astype(np.int16)
    elif method == "trimmed_mean":
        trim = min((count - 1) // 2, max(0, int(count * trim_fraction)))
        ordered = np.sort(stack, axis=0)
        kept = ordered[trim:count - trim] if trim else ordered
        result = np.rint(kept.mean(axis=0)).astype(np.uint8)
        distances = np.abs(stack.astype(np.int16) - result[None].astype(np.int16)).sum(axis=3)
        provenance = np.argmin(distances, axis=0).astype(np.int16)
    elif method == "exact_rgba_mode":
        result, _, provenance = _mode_rows(stack)
    elif method == "rgb_mode_alpha":
        rgb, _, provenance = _mode_rows(stack[:, :, :, :3])
        alpha = np.rint(np.median(stack[:, :, :, 3], axis=0)).astype(np.uint8)
        result = np.dstack((rgb, alpha))
    elif method == "lowest_variance_source":
        median = np.median(stack, axis=0)
        distances = ((stack.astype(np.float32) - median[None]) ** 2).mean(axis=3)
        provenance = np.argmin(distances, axis=0).astype(np.int16)
        yy, xx = np.indices((height, width))
        result = stack[provenance, yy, xx]
    elif method == "source_priority":
        result = stack[0].copy()
        provenance = np.zeros((height, width), dtype=np.int16)
    elif method == "consensus_threshold":
        mode, frequencies, provenance = _mode_rows(stack)
        median = np.rint(np.median(stack, axis=0)).astype(np.uint8)
        result = np.where((frequencies / count >= consensus_threshold)[:, :, None], mode, median)
        med_distances = np.abs(stack.astype(np.int16) - result[None].astype(np.int16)).sum(axis=3)
        provenance = np.argmin(med_distances, axis=0).astype(np.int16)
    else:
        raise ValueError(f"Unknown composite method: {method}")
    return result, provenance


def generate_composite(
    images: list[Image.Image],
    method: str = "median",
    *,
    trim_fraction: float = 0.2,
    consensus_threshold: float = 0.75,
    high_threshold: float = 0.9,
    medium_threshold: float = 0.65,
    region_overrides: list[tuple[np.ndarray, str]] | None = None,
) -> CompositeResult:
    if not images:
        raise ValueError("At least one source image is required")
    size = images[0].size
    if any(image.size != size for image in images):
        raise ValueError("All composite sources must have identical dimensions")
    stack = np.stack([np.asarray(image.convert("RGBA"), dtype=np.uint8) for image in images], axis=0)
    result, provenance = _composite_array(stack, method, trim_fraction, consensus_threshold)
    for mask, override_method in region_overrides or []:
        boolean = np.asarray(mask) > 0
        if boolean.shape != stack.shape[1:3]:
            raise ValueError("Region override mask dimensions do not match")
        override, override_provenance = _composite_array(stack, override_method, trim_fraction, consensus_threshold)
        result[boolean] = override[boolean]
        provenance[boolean] = override_provenance[boolean]

    variance_channels = np.var(stack.astype(np.float32), axis=0)
    variance = variance_channels[:, :, :3].mean(axis=2)
    alpha_variance = variance_channels[:, :, 3]
    maximum_difference = (stack.max(axis=0).astype(np.int16) - stack.min(axis=0).astype(np.int16)).max(axis=2).astype(np.uint8)
    matches = np.all(stack == result[None], axis=3)
    agreement_count = matches.sum(axis=0).astype(np.uint16)
    consensus = agreement_count.astype(np.float32) / len(images)
    confidence = np.zeros(consensus.shape, dtype=np.uint8)
    confidence[consensus >= medium_threshold] = 1
    confidence[consensus >= high_threshold] = 2
    return CompositeResult(
        Image.fromarray(result, "RGBA"), variance, alpha_variance, maximum_difference,
        consensus, agreement_count, provenance, confidence,
    )


def diagnostic_heatmap(values: np.ndarray, maximum: float | None = None) -> Image.Image:
    data = np.asarray(values, dtype=np.float32)
    ceiling = float(maximum if maximum is not None else (np.percentile(data, 99) if data.size else 1))
    normalized = np.clip(data / max(ceiling, 1e-6), 0, 1)
    red = (normalized * 255).astype(np.uint8)
    blue = ((1 - normalized) * 180).astype(np.uint8)
    green = ((1 - np.abs(normalized - 0.5) * 2) * 180).astype(np.uint8)
    return Image.fromarray(np.dstack((red, green, blue, np.full(red.shape, 255, np.uint8))), "RGBA")


def consensus_view(consensus: np.ndarray, high: float = 0.9, medium: float = 0.65) -> Image.Image:
    rgba = np.zeros((*consensus.shape, 4), dtype=np.uint8)
    rgba[:, :, 3] = 255
    rgba[consensus >= high, :3] = (42, 193, 106)
    rgba[(consensus >= medium) & (consensus < high), :3] = (245, 191, 66)
    rgba[(consensus > 0) & (consensus < medium), :3] = (232, 98, 76)
    rgba[consensus == 0, :3] = (90, 50, 120)
    return Image.fromarray(rgba, "RGBA")
