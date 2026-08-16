"""Background-removal errors safe to present in Card Studio."""

from app.utilities.validation import CardStudioError


class BackgroundRemovalError(CardStudioError):
    """Base error for local segmentation and mask processing."""


class ModelMissingError(BackgroundRemovalError):
    """Raised when the packaged model or metadata is absent."""


class ModelValidationError(BackgroundRemovalError):
    """Raised when model metadata, checksum, or ONNX content is invalid."""


class InferenceCancelled(BackgroundRemovalError):
    """Raised at safe cancellation checkpoints."""
