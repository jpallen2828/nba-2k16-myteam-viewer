"""Conservative deterministic alpha-mask post-processing."""

from __future__ import annotations

from dataclasses import asdict, dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass(slots=True)
class MaskPostprocessSettings:
    threshold: int = 0
    edge_softness: float = 0.0
    erosion: int = 0
    dilation: int = 0
    remove_components_smaller_than: int = 0

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict | None) -> "MaskPostprocessSettings":
        data = data or {}
        return cls(
            threshold=max(0, min(254, int(data.get("threshold", 0)))),
            edge_softness=max(0.0, min(20.0, float(data.get("edge_softness", 0.0)))),
            erosion=max(0, min(20, int(data.get("erosion", 0)))),
            dilation=max(0, min(20, int(data.get("dilation", 0)))),
            remove_components_smaller_than=max(
                0, min(100000, int(data.get("remove_components_smaller_than", 0)))
            ),
        )


def postprocess_mask(mask: Image.Image, settings: MaskPostprocessSettings) -> Image.Image:
    values = np.asarray(mask.convert("L"), dtype=np.uint8).copy()
    if settings.threshold:
        values[values < settings.threshold] = 0
    if settings.erosion:
        size = settings.erosion * 2 + 1
        values = cv2.erode(values, np.ones((size, size), np.uint8), iterations=1)
    if settings.dilation:
        size = settings.dilation * 2 + 1
        values = cv2.dilate(values, np.ones((size, size), np.uint8), iterations=1)
    if settings.remove_components_smaller_than:
        binary = (values > 0).astype(np.uint8)
        count, labels, stats, _ = cv2.connectedComponentsWithStats(binary, connectivity=8)
        for label in range(1, count):
            if int(stats[label, cv2.CC_STAT_AREA]) < settings.remove_components_smaller_than:
                values[labels == label] = 0
    if settings.edge_softness:
        sigma = settings.edge_softness
        radius = max(3, int(round(sigma * 3)) * 2 + 1)
        values = cv2.GaussianBlur(values, (radius, radius), sigmaX=sigma, sigmaY=sigma)
    return Image.fromarray(values, mode="L")
