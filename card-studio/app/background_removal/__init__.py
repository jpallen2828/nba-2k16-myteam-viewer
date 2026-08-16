"""Local, non-generative player background-removal services."""

from app.background_removal.cutout_service import apply_alpha_mask, decode_mask_png, encode_mask_png
from app.background_removal.inference_service import BackgroundRemovalInferenceService
from app.background_removal.mask_postprocessing import MaskPostprocessSettings, postprocess_mask

__all__ = [
    "BackgroundRemovalInferenceService",
    "MaskPostprocessSettings",
    "apply_alpha_mask",
    "decode_mask_png",
    "encode_mask_png",
    "postprocess_mask",
]
