"""Cancelable modal progress for local model inference."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QProgressDialog, QWidget


class BackgroundRemovalProgressDialog(QProgressDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__("Loading local model", "Cancel", 0, 0, parent)
        self.setWindowTitle("Remove Background")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumDuration(0)
        self.setAutoClose(False)
        self.setAutoReset(False)
        self.setMinimumWidth(430)

    def set_stage(self, stage: str) -> None:
        self.setLabelText(stage)
