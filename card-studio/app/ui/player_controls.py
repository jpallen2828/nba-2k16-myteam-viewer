"""Minimal player-position controls for the streamlined editor."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtGui import QIntValidator
from PySide6.QtWidgets import QDoubleSpinBox, QFormLayout, QGroupBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from app.models.player_art_model import PlayerTransform


class PlayerControls(QWidget):
    transform_changed = Signal(float, float, float, float, bool)
    text_changed = Signal(str, str, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._updating = False
        self._scale = 1.0
        self._rotation = 0.0
        self._flipped = False
        self.setMinimumWidth(230)
        self.setMaximumWidth(320)

        layout = QVBoxLayout(self)
        position = QGroupBox("Player Position")
        form = QFormLayout(position)
        self.x = self._coordinate_spin()
        self.y = self._coordinate_spin()
        form.addRow("X", self.x)
        form.addRow("Y", self.y)
        layout.addWidget(position)

        card_text = QGroupBox("Card Text")
        text_form = QFormLayout(card_text)
        self.overall = QLineEdit()
        self.overall.setObjectName("overallInput")
        self.overall.setMaxLength(2)
        self.overall.setValidator(QIntValidator(0, 99, self.overall))
        self.overall.setPlaceholderText("97")
        self.position = QLineEdit()
        self.position.setObjectName("positionInput")
        self.position.setMaxLength(2)
        self.position.setPlaceholderText("C")
        self.player_name = QLineEdit()
        self.player_name.setObjectName("playerNameInput")
        self.player_name.setMaxLength(40)
        self.player_name.setPlaceholderText("KAREEM ABDUL-JABBAR")
        text_form.addRow("OVR", self.overall)
        text_form.addRow("Position", self.position)
        text_form.addRow("Player Name", self.player_name)
        layout.addWidget(card_text)

        self.text_warning = QLabel("")
        self.text_warning.setWordWrap(True)
        self.text_warning.setStyleSheet("color:#f0bd63; padding:4px;")
        self.text_warning.hide()
        layout.addWidget(self.text_warning)

        hint = QLabel(
            "Drag the player directly on the card, use X/Y, or press the arrow keys. "
            "Hold Shift for 10-pixel nudges. Hold Ctrl and use the mouse wheel to resize."
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color:#aebbd0; padding:4px;")
        layout.addWidget(hint)
        self.source_dimensions = QLabel("No player image imported")
        self.source_dimensions.setWordWrap(True)
        self.source_dimensions.setStyleSheet("color:#8fa0b5; padding:4px;")
        layout.addWidget(self.source_dimensions)
        layout.addStretch(1)

        self.x.valueChanged.connect(self._emit)
        self.y.valueChanged.connect(self._emit)
        self.overall.textChanged.connect(self._emit_text)
        self.position.textChanged.connect(self._emit_text)
        self.player_name.textChanged.connect(self._emit_text)

    @staticmethod
    def _coordinate_spin() -> QDoubleSpinBox:
        spin = QDoubleSpinBox()
        spin.setRange(-8192.0, 8192.0)
        spin.setDecimals(1)
        spin.setSingleStep(1.0)
        return spin

    def set_transform(self, transform: PlayerTransform) -> None:
        self._updating = True
        self.x.setValue(transform.x)
        self.y.setValue(transform.y)
        self._scale = transform.scale
        self._rotation = transform.rotation_degrees
        self._flipped = transform.flip_horizontal
        self._updating = False

    def set_source_info(self, width: int, height: int, transparent: bool) -> None:
        alpha = "transparent PNG" if transparent else "image has no transparency"
        self.source_dimensions.setText(f"Player image: {width} × {height} px • {alpha}")

    def clear_source_info(self) -> None:
        self.source_dimensions.setText("No player image imported")

    def set_text_values(self, overall: str, position: str, player_name: str) -> None:
        self._updating = True
        self.overall.setText(overall)
        self.position.setText(position)
        self.player_name.setText(player_name)
        self._updating = False

    def set_text_warning(self, warning: str) -> None:
        self.text_warning.setText(warning)
        self.text_warning.setVisible(bool(warning))

    def _emit(self, *_args) -> None:
        if not self._updating:
            self.transform_changed.emit(self.x.value(), self.y.value(), self._scale, self._rotation, self._flipped)

    def _emit_text(self, *_args) -> None:
        if not self._updating:
            self.text_changed.emit(self.overall.text(), self.position.text(), self.player_name.text())
