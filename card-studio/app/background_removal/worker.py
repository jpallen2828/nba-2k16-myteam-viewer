"""Qt thread-pool adapter with cancellation and request identity."""

from __future__ import annotations

import threading

from PIL import Image
from PySide6.QtCore import QObject, QRunnable, Signal, Slot

from app.background_removal.exceptions import InferenceCancelled
from app.background_removal.inference_service import BackgroundRemovalInferenceService
from app.background_removal.mask_postprocessing import MaskPostprocessSettings


class BackgroundRemovalWorkerSignals(QObject):
    stage = Signal(int, str)
    completed = Signal(int, object, float)
    failed = Signal(int, str)
    cancelled = Signal(int)


class BackgroundRemovalWorker(QRunnable):
    def __init__(
        self,
        request_id: int,
        service: BackgroundRemovalInferenceService,
        original: Image.Image,
        settings: MaskPostprocessSettings,
        cancellation: threading.Event,
    ) -> None:
        super().__init__()
        self.request_id = request_id
        self.service = service
        self.original = original.copy()
        self.settings = settings
        self.cancellation = cancellation
        self.signals = BackgroundRemovalWorkerSignals()

    @Slot()
    def run(self) -> None:
        try:
            mask, elapsed = self.service.generate_mask(
                self.original,
                self.settings,
                progress=lambda stage: self.signals.stage.emit(self.request_id, stage),
                cancelled=self.cancellation.is_set,
            )
            if self.cancellation.is_set():
                self.signals.cancelled.emit(self.request_id)
            else:
                self.signals.completed.emit(self.request_id, mask, elapsed)
        except InferenceCancelled:
            self.signals.cancelled.emit(self.request_id)
        except Exception as exc:
            self.signals.failed.emit(self.request_id, str(exc))
