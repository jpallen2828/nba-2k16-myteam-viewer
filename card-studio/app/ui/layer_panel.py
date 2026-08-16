"""Preview-only layer and player-mask diagnostics."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QGroupBox, QLabel, QVBoxLayout, QWidget


class LayerPanel(QWidget):
    options_changed = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        group = QGroupBox("Layers")
        group_layout = QVBoxLayout(group)
        self.foreground = QCheckBox("Foreground")
        self.player = QCheckBox("Player")
        self.background = QCheckBox("Background")
        for item in (self.foreground, self.player, self.background):
            item.setChecked(True)
            item.toggled.connect(self.options_changed)
            group_layout.addWidget(item)
        group_layout.addWidget(QLabel("Player mask diagnostic"))
        self.mask_mode = QComboBox()
        self.mask_mode.addItem("Normal clipped result", "normal")
        self.mask_mode.addItem("Permitted-region overlay", "overlay")
        self.mask_mode.addItem("Mask only", "mask")
        self.mask_mode.currentIndexChanged.connect(self.options_changed)
        group_layout.addWidget(self.mask_mode)
        layout.addWidget(group)

    def values(self) -> tuple[bool, bool, bool, str]:
        return (
            self.background.isChecked(),
            self.player.isChecked(),
            self.foreground.isChecked(),
            str(self.mask_mode.currentData()),
        )

    def set_mask_mode(self, mode: str) -> None:
        index = self.mask_mode.findData(mode)
        self.mask_mode.setCurrentIndex(max(0, index))
