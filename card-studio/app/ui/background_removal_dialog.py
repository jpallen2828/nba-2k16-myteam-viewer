"""Preview and focused refinement dialog for an automatically generated mask."""

from __future__ import annotations

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.background_removal.mask_postprocessing import MaskPostprocessSettings, postprocess_mask
from app.ui.mask_editor_widget import MaskEditorWidget


class BackgroundRemovalDialog(QDialog):
    def __init__(
        self,
        original: Image.Image,
        automatic_mask: Image.Image,
        settings: MaskPostprocessSettings,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Background Removal Preview")
        self.resize(1040, 760)
        self.choice = "cancel"
        self.settings = settings
        layout = QVBoxLayout(self)
        header = QLabel(
            "The cutout uses the untouched imported RGB pixels plus this editable alpha mask. "
            "White preserves the subject; black removes the background."
        )
        header.setWordWrap(True)
        layout.addWidget(header)
        self.editor = MaskEditorWidget(original, automatic_mask)
        layout.addWidget(self.editor, 1)

        self.refinement = QWidget()
        controls = QHBoxLayout(self.refinement)
        self.brush_mode = QComboBox()
        self.brush_mode.addItem("Restore Subject", "restore")
        self.brush_mode.addItem("Remove Background", "remove")
        self.brush_size = QSpinBox(); self.brush_size.setRange(1, 500); self.brush_size.setValue(40); self.brush_size.setSuffix(" px")
        self.brush_strength = QSpinBox(); self.brush_strength.setRange(1, 100); self.brush_strength.setValue(100); self.brush_strength.setSuffix(" %")
        self.soft_edge = QCheckBox("Soft edge"); self.soft_edge.setChecked(True)
        self.view = QComboBox()
        self.view.addItem("Show Cutout", "cutout")
        self.view.addItem("Show Original", "original")
        self.view.addItem("Show Mask", "mask")
        self.view.addItem("Red Overlay", "overlay")
        for widget in (self.brush_mode, self.brush_size, self.brush_strength, self.soft_edge, self.view):
            controls.addWidget(widget)
        for label, callback in (("Undo", self.editor.undo), ("Redo", self.editor.redo), ("Reset Automatic", self.editor.reset_automatic), ("Fit", self.editor.fit_view), ("Actual Pixels", self.editor.set_actual_pixels)):
            button = QPushButton(label); button.clicked.connect(callback); controls.addWidget(button)
        layout.addWidget(self.refinement)

        edge_controls = QWidget()
        edge_form = QFormLayout(edge_controls)
        edge_form.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapLongRows)
        self.threshold = QSpinBox(); self.threshold.setRange(0, 254); self.threshold.setValue(settings.threshold)
        self.softness = QDoubleSpinBox(); self.softness.setRange(0, 20); self.softness.setDecimals(1); self.softness.setValue(settings.edge_softness)
        self.erosion = QSpinBox(); self.erosion.setRange(0, 20); self.erosion.setValue(settings.erosion)
        self.dilation = QSpinBox(); self.dilation.setRange(0, 20); self.dilation.setValue(settings.dilation)
        self.components = QSpinBox(); self.components.setRange(0, 100000); self.components.setValue(settings.remove_components_smaller_than); self.components.setSuffix(" px")
        apply_settings = QPushButton("Apply Edge Settings")
        apply_settings.clicked.connect(self._apply_settings)
        row = QHBoxLayout()
        for label, widget in (("Threshold", self.threshold), ("Softness", self.softness), ("Erode", self.erosion), ("Dilate", self.dilation), ("Remove islands under", self.components)):
            row.addWidget(QLabel(label)); row.addWidget(widget)
        row.addWidget(apply_settings)
        edge_form.addRow(row)
        layout.addWidget(edge_controls)

        buttons = QHBoxLayout()
        self.refine_button = QPushButton("Refine Mask")
        accept = QPushButton("Accept Cutout"); accept.setObjectName("primaryButton")
        retry = QPushButton("Retry")
        restore = QPushButton("Restore Original")
        cancel = QPushButton("Cancel")
        for button in (self.refine_button, accept, retry, restore, cancel):
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.refine_button.clicked.connect(self._toggle_refinement)
        accept.clicked.connect(lambda: self._finish("accept"))
        retry.clicked.connect(lambda: self._finish("retry"))
        restore.clicked.connect(lambda: self._finish("restore"))
        cancel.clicked.connect(self.reject)
        self.brush_mode.currentIndexChanged.connect(self._sync_brush)
        self.brush_size.valueChanged.connect(self._sync_brush)
        self.brush_strength.valueChanged.connect(self._sync_brush)
        self.soft_edge.toggled.connect(self._sync_brush)
        self.view.currentIndexChanged.connect(lambda: self.editor.set_view_mode(str(self.view.currentData())))
        self.refinement.hide()
        edge_controls.hide()
        self.edge_controls = edge_controls
        self._sync_brush()

    def accepted_mask(self) -> Image.Image:
        return self.editor.current_mask()

    def was_manually_edited(self) -> bool:
        return self.editor.is_modified()

    def _toggle_refinement(self) -> None:
        visible = not self.refinement.isVisible()
        self.refinement.setVisible(visible)
        self.edge_controls.setVisible(visible)
        self.refine_button.setText("Hide Refinement" if visible else "Refine Mask")

    def _sync_brush(self, *_args) -> None:
        self.editor.set_brush(str(self.brush_mode.currentData()), self.brush_size.value(), self.brush_strength.value() / 100.0, self.soft_edge.isChecked())

    def _apply_settings(self) -> None:
        self.settings = MaskPostprocessSettings(self.threshold.value(), self.softness.value(), self.erosion.value(), self.dilation.value(), self.components.value())
        self.editor.replace_from_automatic(postprocess_mask(self.editor.automatic_mask, self.settings))

    def _finish(self, choice: str) -> None:
        self.choice = choice
        self.accept()
