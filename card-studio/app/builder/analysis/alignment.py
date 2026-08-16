"""Deterministic OpenCV alignment proposals that never mutate project state."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np
from PIL import Image


@dataclass(frozen=True, slots=True)
class AlignmentProposal:
    translate_x: float
    translate_y: float
    rotation_degrees: float
    scale: float
    confidence: float
    method: str
    integer_only: bool
    warning: str | None = None


def _gray(image: Image.Image) -> np.ndarray:
    rgba = np.asarray(image.convert("RGBA"), dtype=np.uint8)
    rgb = rgba[:, :, :3]
    return cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY).astype(np.float32) / 255.0


def propose_alignment(
    reference: Image.Image,
    moving: Image.Image,
    mask: np.ndarray | Image.Image | None = None,
    integer_only: bool = True,
    allow_rotation_scale: bool = True,
) -> AlignmentProposal:
    if reference.size != moving.size:
        raise ValueError("Alignment images must have identical working dimensions")
    fixed = _gray(reference)
    candidate = _gray(moving)
    mask_array: np.ndarray | None = None
    if mask is not None:
        mask_array = np.asarray(mask.convert("L") if isinstance(mask, Image.Image) else mask, dtype=np.uint8)
        if mask_array.shape != fixed.shape:
            raise ValueError("Alignment mask dimensions do not match the working canvas")
        weight = mask_array.astype(np.float32) / 255.0
        fixed = fixed * weight
        candidate = candidate * weight

    # Phase correlation is stable for exact integer shifts and provides a useful seed.
    (phase_x, phase_y), phase_score = cv2.phaseCorrelate(candidate, fixed)
    matrix = np.asarray(((1.0, 0.0, phase_x), (0.0, 1.0, phase_y)), dtype=np.float32)
    method = "phase-correlation"
    confidence = float(max(0.0, min(1.0, phase_score)))
    if allow_rotation_scale:
        try:
            criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 100, 1e-6)
            score, matrix = cv2.findTransformECC(
                fixed,
                candidate,
                matrix,
                cv2.MOTION_AFFINE,
                criteria,
                inputMask=mask_array,
                gaussFiltSize=3,
            )
            # ECC matrix maps input to template; invert to match our render transform convention.
            matrix = cv2.invertAffineTransform(matrix)
            confidence = float(max(0.0, min(1.0, score)))
            method = "ecc-affine"
        except cv2.error:
            matrix = np.asarray(((1.0, 0.0, phase_x), (0.0, 1.0, phase_y)), dtype=np.float32)

    a, b = float(matrix[0, 0]), float(matrix[0, 1])
    scale = float((a * a + b * b) ** 0.5)
    # OpenCV's affine angle is the physical correction. SourceTransform uses
    # the opposite sign because normalize_source passes -rotation to OpenCV.
    rotation = float(-np.degrees(np.arctan2(b, a)))
    tx, ty = float(matrix[0, 2]), float(matrix[1, 2])
    if method == "ecc-affine":
        center_x, center_y = (reference.width - 1) / 2, (reference.height - 1) / 2
        # Convert origin-based affine translation to our center-based controls.
        tx -= (1 - a) * center_x - b * center_y
        ty -= b * center_x + (1 - a) * center_y
    warning = None
    if abs(tx) > reference.width * 0.25 or abs(ty) > reference.height * 0.25 or not 0.8 <= scale <= 1.2 or abs(rotation) > 15:
        warning = "Proposed transform exceeds safe minor-alignment limits; review manually."
    elif confidence < 0.35:
        warning = "Low-confidence alignment; inspect overlay and difference views before accepting."
    if integer_only:
        tx, ty = float(round(tx)), float(round(ty))
        scale = 1.0
        rotation = 0.0
    return AlignmentProposal(tx, ty, rotation, scale, confidence, method, integer_only, warning)
