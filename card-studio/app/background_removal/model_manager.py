"""Lazy, cached ONNX session loading with integrity and provider checks."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from threading import Lock

import onnxruntime as ort

from app.background_removal.exceptions import ModelMissingError, ModelValidationError
from app.background_removal.model_metadata import ModelMetadata


class BackgroundRemovalModelManager:
    def __init__(self, model_directory: Path, logger: logging.Logger | None = None) -> None:
        self.model_directory = model_directory.resolve()
        self.logger = logger or logging.getLogger(__name__)
        self.metadata = ModelMetadata.load(self.model_directory / "model.json")
        self.model_path = self.model_directory / self.metadata.filename
        self._session: ort.InferenceSession | None = None
        self._lock = Lock()
        self.provider = "not loaded"

    def validate_model(self) -> None:
        if not self.model_path.is_file():
            raise ModelMissingError(
                f"The local background-removal model is missing:\n{self.model_path}\n\n"
                "Transparent PNG importing will continue to work normally."
            )
        digest = hashlib.sha256()
        try:
            with self.model_path.open("rb") as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(block)
        except OSError as exc:
            raise ModelValidationError(f"Could not read the background-removal model: {exc}") from exc
        if digest.hexdigest().lower() != self.metadata.sha256:
            raise ModelValidationError(
                "The packaged background-removal model failed its SHA-256 integrity check. "
                "Normal image importing is still available."
            )

    def session(self) -> ort.InferenceSession:
        if self._session is not None:
            return self._session
        with self._lock:
            if self._session is not None:
                return self._session
            self.validate_model()
            providers = self._providers()
            options = ort.SessionOptions()
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
            options.intra_op_num_threads = 0
            try:
                self._session = ort.InferenceSession(
                    str(self.model_path), sess_options=options, providers=providers
                )
            except Exception as exc:  # ONNX Runtime exposes several provider-specific exception types.
                raise ModelValidationError(f"Could not load the local ONNX model: {exc}") from exc
            self.provider = self._session.get_providers()[0]
            self.logger.info("Loaded background-removal model %s with %s", self.metadata.name, self.provider)
            return self._session

    @staticmethod
    def _providers() -> list[str]:
        available = set(ort.get_available_providers())
        for accelerated in (
            "DmlExecutionProvider",
            "CUDAExecutionProvider",
            "ROCMExecutionProvider",
            "OpenVINOExecutionProvider",
        ):
            if accelerated in available:
                return [accelerated, "CPUExecutionProvider"]
        return ["CPUExecutionProvider"]
