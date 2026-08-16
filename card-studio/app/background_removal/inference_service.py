"""Dedicated deterministic ONNX inference service."""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter

import numpy as np
from PIL import Image

from app.background_removal.exceptions import InferenceCancelled, ModelValidationError
from app.background_removal.mask_postprocessing import MaskPostprocessSettings, postprocess_mask
from app.background_removal.model_manager import BackgroundRemovalModelManager


ProgressCallback = Callable[[str], None]
CancelCheck = Callable[[], bool]


class BackgroundRemovalInferenceService:
    def __init__(self, model_manager: BackgroundRemovalModelManager) -> None:
        self.model_manager = model_manager

    def generate_mask(
        self,
        original: Image.Image,
        settings: MaskPostprocessSettings | None = None,
        progress: ProgressCallback | None = None,
        cancelled: CancelCheck | None = None,
    ) -> tuple[Image.Image, float]:
        progress = progress or (lambda _stage: None)
        cancelled = cancelled or (lambda: False)
        self._cancel_checkpoint(cancelled)
        progress("Loading local model")
        session = self.model_manager.session()
        self._cancel_checkpoint(cancelled)
        progress("Analyzing player image")
        metadata = self.model_manager.metadata
        rgb = original.convert("RGB").resize(metadata.input_size, Image.Resampling.LANCZOS)
        values = np.asarray(rgb, dtype=np.float32) / 255.0
        values = (values - np.asarray(metadata.mean, dtype=np.float32)) / np.asarray(
            metadata.std, dtype=np.float32
        )
        tensor = np.transpose(values, (2, 0, 1))[None, ...].astype(np.float32, copy=False)
        input_name = session.get_inputs()[0].name
        started = perf_counter()
        try:
            output = session.run(None, {input_name: tensor})[0]
        except Exception as exc:
            raise ModelValidationError(f"Local ONNX inference failed: {exc}") from exc
        elapsed = perf_counter() - started
        self._cancel_checkpoint(cancelled)
        progress("Creating transparency mask")
        logits = np.asarray(output, dtype=np.float32)
        while logits.ndim > 2:
            logits = logits[0]
        logits = np.clip(logits, -80.0, 80.0)
        prediction = 1.0 / (1.0 + np.exp(-logits))
        low, high = float(prediction.min()), float(prediction.max())
        if high <= low:
            raise ModelValidationError("The local model returned a constant mask.")
        prediction = (prediction - low) / (high - low)
        mask = Image.fromarray(np.rint(prediction * 255.0).astype(np.uint8), mode="L")
        mask = mask.resize(original.size, Image.Resampling.LANCZOS)
        self._cancel_checkpoint(cancelled)
        progress("Refining edges")
        mask = postprocess_mask(mask, settings or MaskPostprocessSettings())
        self._cancel_checkpoint(cancelled)
        progress("Preparing preview")
        return mask, elapsed

    @staticmethod
    def _cancel_checkpoint(cancelled: CancelCheck) -> None:
        if cancelled():
            raise InferenceCancelled("Background removal was cancelled.")
