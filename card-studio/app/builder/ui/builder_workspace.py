"""Functional Template Builder workspace and its non-destructive workflows."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
from PIL import Image
from PySide6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
    QDoubleSpinBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
    QProgressBar, QPushButton, QScrollArea, QSpinBox, QSplitter, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

from app.builder.analysis.alignment import propose_alignment
from app.builder.analysis.composite import COMPOSITE_METHODS
from app.builder.analysis.normalization import normalize_source
from app.builder.models import BuilderProject, PatchOperation, RegionOverride, SourceTransform
from app.builder.rendering import DISPLAY_MODES, BuilderRenderState, BuilderRenderer
from app.builder.services.autosave_service import AutosaveService
from app.builder.services.history_service import HistoryService
from app.builder.services.project_service import BuilderProjectError, BuilderProjectService
from app.builder.services.source_service import SourceImportError, SourceService
from app.builder.services.template_export_service import TemplateExportError, TemplateExportService
from app.builder.ui.builder_canvas import BuilderCanvas
from app.constants import BUILDER_PROJECT_EXTENSION, SUPPORTED_SOURCE_FORMATS
from app.services.settings_service import SettingsService
from app.ui.canvas_widget import pil_to_qimage
from app.utilities.paths import AppPaths
from app.utilities.validation import SAFE_TEMPLATE_ID


class WorkerSignals(QObject):
    result = Signal(int, object)
    error = Signal(int, str)
    finished = Signal(int)


class AnalysisWorker(QRunnable):
    def __init__(self, generation: int, renderer: BuilderRenderer, project: BuilderProject) -> None:
        super().__init__()
        self.generation = generation
        self.renderer = renderer
        self.project = project
        self.signals = WorkerSignals()
        self.cancelled = False

    def run(self) -> None:
        try:
            if not self.cancelled:
                state = self.renderer.build_state(self.project)
                if not self.cancelled:
                    self.signals.result.emit(self.generation, state)
        except Exception as exc:  # worker errors are returned to the GUI/log
            self.signals.error.emit(self.generation, str(exc))
        finally:
            self.signals.finished.emit(self.generation)


class BuilderWorkspace(QWidget):
    """Coordinates Builder services while keeping analysis testable without Qt."""

    project_changed = Signal(str, bool)
    template_exported = Signal(str)

    def __init__(self, paths: AppPaths, settings: SettingsService, logger: logging.Logger, parent=None) -> None:
        super().__init__(parent)
        self.paths, self.settings, self.logger = paths, settings, logger
        self.source_service = SourceService()
        self.project_service = BuilderProjectService(paths.builder_backups)
        self.autosave_service = AutosaveService(paths.builder_autosaves)
        self.export_service = TemplateExportService()
        self.renderer = BuilderRenderer(self.source_service)
        self.history = HistoryService(60)
        self.project: BuilderProject | None = None
        self.state: BuilderRenderState | None = None
        self._generation = 0
        self._worker: AnalysisWorker | None = None
        self._stroke_before: dict | None = None
        self._stroke_points: set[tuple[int, int]] = set()
        self._flicker = False
        self._sample_player: Image.Image | None = None
        self._cursor_xy: tuple[int, int] | None = None
        self._text_rgba = [255, 255, 255, 255]
        self._build_ui()
        self._connect()
        self._autosave_timer = QTimer(self)
        interval = int(self.settings.value("builder/autosave_minutes", 3) or 3)
        self._autosave_timer.setInterval(max(1, interval) * 60_000)
        self._autosave_timer.timeout.connect(self.autosave)
        self._autosave_timer.start()
        self._flicker_timer = QTimer(self)
        self._flicker_timer.setInterval(450)
        self._flicker_timer.timeout.connect(self._toggle_flicker)
        self._flicker_timer.start()
        QTimer.singleShot(50, self._offer_recovery)

    # ---- UI construction -------------------------------------------------
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        banner = QLabel("Template Builder — authentic-source extraction; no generative reconstruction")
        banner.setStyleSheet("color:#91a9c4; padding:4px")
        root.addWidget(banner)
        splitter = QSplitter()
        root.addWidget(splitter, 1)

        left_scroll = QScrollArea(); left_scroll.setWidgetResizable(True); left = QWidget(); left_scroll.setWidget(left)
        left_layout = QVBoxLayout(left)
        source_group = QGroupBox("Source Cards")
        source_layout = QVBoxLayout(source_group)
        self.source_list = QListWidget(); self.source_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        source_layout.addWidget(self.source_list)
        self.source_info = QLabel("No sources imported"); self.source_info.setWordWrap(True)
        source_layout.addWidget(self.source_info)
        grid = QGridLayout()
        buttons = [
            ("Import…", "import_source_button"), ("Rename", "rename_source_button"),
            ("Set reference", "reference_button"), ("Show / hide", "visibility_button"),
            ("Isolate", "isolate_button"), ("Remove", "remove_source_button"),
            ("Move up", "up_button"), ("Move down", "down_button"),
            ("Relink…", "relink_button"), ("Open location", "open_location_button"),
        ]
        for index, (label, attr) in enumerate(buttons):
            button = QPushButton(label); setattr(self, attr, button); grid.addWidget(button, index // 2, index % 2)
        source_layout.addLayout(grid)
        left_layout.addWidget(source_group)

        transform_group = QGroupBox("Normalization & Alignment")
        transform_form = QFormLayout(transform_group)
        self.tx = QDoubleSpinBox(); self.ty = QDoubleSpinBox(); self.scale = QDoubleSpinBox(); self.rotation = QDoubleSpinBox()
        for widget in (self.tx, self.ty): widget.setRange(-10000, 10000); widget.setDecimals(2)
        self.scale.setRange(0.05, 5); self.scale.setDecimals(5); self.scale.setValue(1)
        self.rotation.setRange(-180, 180); self.rotation.setDecimals(3)
        self.subpixel = QCheckBox("Allow subpixel resampling")
        self.apply_transform_button = QPushButton("Apply manual transform")
        self.normalize_button = QPushButton("Crop / four corners…")
        self.auto_align_button = QPushButton("Propose automatic alignment")
        self.reset_transform_button = QPushButton("Reset transform")
        transform_form.addRow("X translation", self.tx); transform_form.addRow("Y translation", self.ty)
        transform_form.addRow("Scale", self.scale); transform_form.addRow("Rotation", self.rotation)
        transform_form.addRow(self.subpixel); transform_form.addRow(self.apply_transform_button)
        transform_form.addRow(self.normalize_button); transform_form.addRow(self.auto_align_button); transform_form.addRow(self.reset_transform_button)
        left_layout.addWidget(transform_group); left_layout.addStretch(1)

        center = QWidget(); center_layout = QVBoxLayout(center); center_layout.setContentsMargins(2, 2, 2, 2)
        view_row = QHBoxLayout()
        self.view_mode = QComboBox(); self.view_mode.addItems(DISPLAY_MODES)
        self.overlay_opacity = QDoubleSpinBox(); self.overlay_opacity.setRange(0, 1); self.overlay_opacity.setSingleStep(.05); self.overlay_opacity.setValue(.5)
        self.generate_button = QPushButton("Generate / Refresh")
        self.cancel_button = QPushButton("Cancel"); self.cancel_button.setEnabled(False)
        view_row.addWidget(QLabel("View")); view_row.addWidget(self.view_mode, 1); view_row.addWidget(QLabel("Overlay")); view_row.addWidget(self.overlay_opacity)
        view_row.addWidget(self.generate_button); view_row.addWidget(self.cancel_button)
        center_layout.addLayout(view_row)
        self.canvas = BuilderCanvas(); center_layout.addWidget(self.canvas, 1)
        self.progress = QProgressBar(); self.progress.setRange(0, 0); self.progress.hide(); center_layout.addWidget(self.progress)
        self.pixel_status = QLabel("Pixel: — | Reference: — | Selected: — | Candidate: — | Final: —")
        self.pixel_status.setTextInteractionFlags(self.pixel_status.textInteractionFlags())
        center_layout.addWidget(self.pixel_status)

        right_scroll = QScrollArea(); right_scroll.setWidgetResizable(True); right = QWidget(); right_scroll.setWidget(right)
        right_layout = QVBoxLayout(right)
        tabs = QTabWidget(); right_layout.addWidget(tabs); right_layout.addStretch(1)
        tabs.addTab(self._composite_tab(), "Composite")
        tabs.addTab(self._mask_tab(), "Masks / Pixels")
        tabs.addTab(self._text_tab(), "Text Regions")
        tabs.addTab(self._history_tab(), "History")
        tabs.addTab(self._finalize_tab(), "Finalize")
        splitter.addWidget(left_scroll); splitter.addWidget(center); splitter.addWidget(right_scroll)
        splitter.setSizes([300, 800, 340]); splitter.setStretchFactor(1, 1)

    def _composite_tab(self) -> QWidget:
        page = QWidget(); form = QFormLayout(page)
        self.composite_method = QComboBox(); self.composite_method.addItems(COMPOSITE_METHODS)
        self.trim_fraction = QDoubleSpinBox(); self.trim_fraction.setRange(0, .45); self.trim_fraction.setValue(.2); self.trim_fraction.setSingleStep(.05)
        self.consensus_threshold = QDoubleSpinBox(); self.consensus_threshold.setRange(0, 1); self.consensus_threshold.setValue(.75); self.consensus_threshold.setSingleStep(.05)
        self.high_threshold = QDoubleSpinBox(); self.high_threshold.setRange(0, 1); self.high_threshold.setValue(.9)
        self.medium_threshold = QDoubleSpinBox(); self.medium_threshold.setRange(0, 1); self.medium_threshold.setValue(.65)
        form.addRow("Global method", self.composite_method); form.addRow("Trim fraction", self.trim_fraction)
        form.addRow("Consensus threshold", self.consensus_threshold); form.addRow("High confidence", self.high_threshold); form.addRow("Medium confidence", self.medium_threshold)
        self.override_mask = QComboBox(); self.override_mask.addItems(("overall_text", "position_text", "player_name", "logo", "stable_frame", "variable_exclusion"))
        self.override_method = QComboBox(); self.override_method.addItems(COMPOSITE_METHODS)
        self.add_override_button = QPushButton("Add / replace region override")
        self.override_list = QListWidget()
        form.addRow("Override mask", self.override_mask); form.addRow("Override method", self.override_method); form.addRow(self.add_override_button); form.addRow(self.override_list)
        return page

    def _mask_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); form = QFormLayout()
        self.edit_mode = QComboBox(); self.edit_mode.addItems(("Mask", "Source patch", "Manual pixel"))
        self.mask_name = QComboBox(); self.mask_name.addItems((
            "alignment", "stable_frame", "variable_exclusion", "player_art", "foreground", "background",
            "overall_text", "position_text", "player_name", "logo", "protected", "unresolved",
        ))
        self.mask_tool = QComboBox(); self.mask_tool.addItems(("Brush", "Eraser", "Rectangle", "Ellipse", "Flood fill"))
        self.brush_size = QSpinBox(); self.brush_size.setRange(1, 255); self.brush_size.setValue(1)
        self.mask_alpha = QSpinBox(); self.mask_alpha.setRange(0, 255); self.mask_alpha.setValue(255)
        self.feather_amount = QSpinBox(); self.feather_amount.setRange(0, 64); self.feather_amount.setValue(0)
        self.mask_visible = QCheckBox("Show selected mask overlay"); self.mask_visible.setChecked(True)
        self.keep_masks_visible = QCheckBox("Keep other visible masks")
        self.pixel_color = QPushButton("Manual RGBA: 255,255,255,255"); self._manual_rgba = [255, 255, 255, 255]
        self.offset_patch = QCheckBox("Enable offset patching")
        self.offset_x = QSpinBox(); self.offset_x.setRange(-9999, 9999); self.offset_y = QSpinBox(); self.offset_y.setRange(-9999, 9999)
        form.addRow("Editing mode", self.edit_mode); form.addRow("Named mask", self.mask_name); form.addRow("Mask tool", self.mask_tool)
        form.addRow("Integer brush size", self.brush_size); form.addRow("Mask alpha", self.mask_alpha); form.addRow("Explicit feather radius", self.feather_amount); form.addRow(self.mask_visible); form.addRow(self.keep_masks_visible)
        form.addRow(self.pixel_color); form.addRow(self.offset_patch); form.addRow("Source offset X", self.offset_x); form.addRow("Source offset Y", self.offset_y)
        layout.addLayout(form)
        row = QHBoxLayout(); self.invert_mask_button = QPushButton("Invert"); self.fill_mask_button = QPushButton("Fill"); self.clear_mask_button = QPushButton("Clear")
        row.addWidget(self.invert_mask_button); row.addWidget(self.fill_mask_button); row.addWidget(self.clear_mask_button); layout.addLayout(row)
        row2 = QHBoxLayout(); self.feather_mask_button = QPushButton("Apply feather"); self.polygon_mask_button = QPushButton("Polygon from coordinates…"); row2.addWidget(self.feather_mask_button); row2.addWidget(self.polygon_mask_button); layout.addLayout(row2)
        row3 = QHBoxLayout(); self.copy_selected_button = QPushButton("Pick selected"); self.copy_reference_button = QPushButton("Pick reference"); self.copy_candidate_button = QPushButton("Pick candidate"); row3.addWidget(self.copy_selected_button); row3.addWidget(self.copy_reference_button); row3.addWidget(self.copy_candidate_button); layout.addLayout(row3)
        note = QLabel("Left-drag paints; right-drag erases. Source patches default to the same coordinate. Manual RGBA pixels remain separately identified in provenance.")
        note.setWordWrap(True); layout.addWidget(note); layout.addStretch(1)
        return page

    def _text_tab(self) -> QWidget:
        page = QWidget(); form = QFormLayout(page)
        self.text_field = QComboBox(); self.text_field.addItems(("overall", "position", "name"))
        self.text_x = QSpinBox(); self.text_y = QSpinBox(); self.text_w = QSpinBox(); self.text_h = QSpinBox(); self.text_baseline = QSpinBox(); self.text_max_width = QSpinBox()
        for widget in (self.text_x, self.text_y, self.text_w, self.text_h, self.text_baseline, self.text_max_width): widget.setRange(-1, 10000)
        self.text_halign = QComboBox(); self.text_halign.addItems(("left", "center", "right"))
        self.text_valign = QComboBox(); self.text_valign.addItems(("top", "center", "bottom", "baseline"))
        self.text_clean = QCheckBox("Region is clean")
        self.text_color = QPushButton("Expected RGBA: 255,255,255,255")
        self.text_notes = QTextEdit(); self.text_notes.setMaximumHeight(80)
        self.save_text_button = QPushButton("Save text-region definition")
        for label, widget in (("Field", self.text_field), ("X", self.text_x), ("Y", self.text_y), ("Width", self.text_w), ("Height", self.text_h), ("Baseline (-1 none)", self.text_baseline), ("Maximum width", self.text_max_width), ("Horizontal", self.text_halign), ("Vertical", self.text_valign)):
            form.addRow(label, widget)
        form.addRow(self.text_clean); form.addRow(self.text_color); form.addRow("Notes", self.text_notes); form.addRow(self.save_text_button)
        return page

    def _history_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page); self.history_list = QListWidget(); layout.addWidget(self.history_list)
        row = QHBoxLayout(); self.undo_button = QPushButton("Undo"); self.redo_button = QPushButton("Redo"); row.addWidget(self.undo_button); row.addWidget(self.redo_button); layout.addLayout(row)
        return page

    def _finalize_tab(self) -> QWidget:
        page = QWidget(); layout = QVBoxLayout(page)
        self.autosave_minutes = QSpinBox(); self.autosave_minutes.setRange(1, 120); self.autosave_minutes.setValue(int(self.settings.value("builder/autosave_minutes", 3) or 3))
        autosave_row = QHBoxLayout(); autosave_row.addWidget(QLabel("Autosave interval (minutes)")); autosave_row.addWidget(self.autosave_minutes)
        self.sample_button = QPushButton("Load temporary sample player…")
        self.validate_button = QPushButton("Run final validation")
        self.export_button = QPushButton("Export v2 template package…")
        self.final_report = QTextEdit(); self.final_report.setReadOnly(True); self.final_report.setMinimumHeight(180)
        layout.addLayout(autosave_row); layout.addWidget(self.sample_button); layout.addWidget(self.validate_button); layout.addWidget(self.export_button); layout.addWidget(self.final_report); layout.addStretch(1)
        return page

    def _connect(self) -> None:
        self.source_list.currentRowChanged.connect(self._source_selected)
        self.import_source_button.clicked.connect(self.import_sources); self.rename_source_button.clicked.connect(self.rename_source)
        self.reference_button.clicked.connect(self.set_reference); self.visibility_button.clicked.connect(self.toggle_source)
        self.isolate_button.clicked.connect(self.isolate_source); self.remove_source_button.clicked.connect(self.remove_source)
        self.up_button.clicked.connect(lambda: self.move_source(-1)); self.down_button.clicked.connect(lambda: self.move_source(1))
        self.relink_button.clicked.connect(self.relink_source); self.open_location_button.clicked.connect(self.open_source_location)
        self.apply_transform_button.clicked.connect(self.apply_transform); self.reset_transform_button.clicked.connect(self.reset_transform)
        self.normalize_button.clicked.connect(self.normalize_source_dialog); self.auto_align_button.clicked.connect(self.auto_align)
        self.generate_button.clicked.connect(self.generate); self.cancel_button.clicked.connect(self.cancel_generation)
        self.view_mode.currentTextChanged.connect(self.refresh_view); self.overlay_opacity.valueChanged.connect(self.refresh_view)
        self.composite_method.currentTextChanged.connect(self._apply_composite_settings)
        for widget in (self.trim_fraction, self.consensus_threshold, self.high_threshold, self.medium_threshold): widget.valueChanged.connect(self._apply_composite_settings)
        self.add_override_button.clicked.connect(self.add_region_override)
        self.mask_name.currentTextChanged.connect(self._mask_selection_changed); self.mask_tool.currentTextChanged.connect(self._tool_changed)
        self.mask_visible.toggled.connect(self._mask_visibility_changed); self.pixel_color.clicked.connect(self.choose_manual_color)
        self.invert_mask_button.clicked.connect(lambda: self._mask_action("invert")); self.fill_mask_button.clicked.connect(lambda: self._mask_action("fill")); self.clear_mask_button.clicked.connect(lambda: self._mask_action("clear"))
        self.feather_mask_button.clicked.connect(self.feather_mask); self.polygon_mask_button.clicked.connect(self.polygon_mask)
        self.copy_selected_button.clicked.connect(lambda: self.pick_pixel("selected")); self.copy_reference_button.clicked.connect(lambda: self.pick_pixel("reference")); self.copy_candidate_button.clicked.connect(lambda: self.pick_pixel("candidate"))
        self.canvas.edit_started.connect(self._edit_started); self.canvas.edit_point.connect(self._edit_point); self.canvas.edit_rectangle.connect(self._edit_rectangle); self.canvas.edit_finished.connect(self._edit_finished)
        self.canvas.cursor_pixel.connect(self._pixel_moved); self.canvas.nudge_requested.connect(self.nudge_source)
        self.text_field.currentTextChanged.connect(self._load_text_region); self.save_text_button.clicked.connect(self.save_text_region)
        self.text_color.clicked.connect(self.choose_text_color); self.autosave_minutes.valueChanged.connect(self._set_autosave_interval)
        self.undo_button.clicked.connect(self.undo); self.redo_button.clicked.connect(self.redo)
        self.sample_button.clicked.connect(self.load_sample_player); self.validate_button.clicked.connect(self.show_validation); self.export_button.clicked.connect(self.export_template)

    # ---- project lifecycle ----------------------------------------------
    def new_project(self) -> bool:
        if not self._maybe_continue(): return False
        dialog = QDialog(self); dialog.setWindowTitle("New Template Builder Project"); form = QFormLayout(dialog)
        tier = QLineEdit("New Tier"); template_id = QLineEdit("new_tier")
        width = QSpinBox(); width.setRange(1, 10000); width.setValue(512)
        height = QSpinBox(); height.setRange(1, 10000); height.setValue(768)
        status = QComboBox(); status.addItems(("working", "verified-original", "template-matched"))
        use_image = QPushButton("Use exact dimensions of a reference image…")
        existing = QComboBox(); existing.addItem("(none — keep entered dimensions)", None)
        for definition_path in sorted(self.paths.templates.glob("*/template.json")):
            try:
                definition = json.loads(definition_path.read_text(encoding="utf-8-sig"))
                canvas = definition["canvas"]
                existing.addItem(str(definition.get("display_name") or definition_path.parent.name), (int(canvas["width"]), int(canvas["height"])))
            except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
                pass
        warning = QLabel("Use exact cropped-reference dimensions when available. Scaling a screenshot does not recover the game's internal asset resolution."); warning.setWordWrap(True)
        form.addRow("Tier display name", tier); form.addRow("Template ID", template_id); form.addRow("Working width", width); form.addRow("Working height", height); form.addRow(use_image); form.addRow("Match existing template", existing); form.addRow("Resolution status", status); form.addRow(warning)
        def image_dimensions() -> None:
            filename, _ = QFileDialog.getOpenFileName(dialog, "Choose cropped reference card", str(self.paths.user_data), "Images (*.png *.webp *.tif *.tiff *.bmp *.jpg *.jpeg)")
            if filename:
                with Image.open(filename) as opened:
                    width.setValue(opened.width); height.setValue(opened.height)
                status.setCurrentText("working")
        def existing_dimensions(index: int) -> None:
            values = existing.itemData(index)
            if values:
                width.setValue(values[0]); height.setValue(values[1]); status.setCurrentText("template-matched")
        use_image.clicked.connect(image_dimensions); existing.currentIndexChanged.connect(existing_dimensions)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject); form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted: return False
        if not SAFE_TEMPLATE_ID.fullmatch(template_id.text().strip()):
            QMessageBox.warning(self, "Invalid template ID", "Use lowercase letters, numbers, underscores, and hyphens only."); return False
        self.project = BuilderProject.create(tier.text(), template_id.text(), width.value(), height.value())
        self.project.resolution_status = status.currentText(); self.state = None; self.history = HistoryService(60); self.renderer.invalidate(); self._sync_all(); self.generate()
        self.logger.info("Created Builder project %s (%sx%s)", self.project.template_id, self.project.width, self.project.height)
        return True

    def open_project(self) -> bool:
        if not self._maybe_continue(): return False
        start = str(self.settings.value("builder/project_path", self.paths.builder_projects))
        filename, _ = QFileDialog.getOpenFileName(self, "Open Template Builder Project", start, f"Builder Projects (*{BUILDER_PROJECT_EXTENSION})")
        if not filename: return False
        try:
            self.project = self.project_service.load(Path(filename)); self.state = None; self.history = HistoryService(60); self.renderer.invalidate(); self.settings.set_value("builder/project_path", str(Path(filename).parent)); self._sync_all(); self.generate()
            missing = self.project_service.missing_sources(self.project)
            if missing: QMessageBox.warning(self, "Missing source cards", f"{len(missing)} source(s) are missing. Select each one and use Relink.")
            self.logger.info("Opened Builder project %s", filename); return True
        except BuilderProjectError as exc:
            QMessageBox.critical(self, "Could not open Builder project", str(exc)); return False

    def save_project(self, save_as: bool = False) -> bool:
        if not self.project: return False
        path = self.project.file_path
        if save_as or path is None:
            start = path or self.paths.builder_projects / f"{self.project.template_id}{BUILDER_PROJECT_EXTENSION}"
            filename, _ = QFileDialog.getSaveFileName(self, "Save Template Builder Project", str(start), f"Builder Projects (*{BUILDER_PROJECT_EXTENSION})")
            if not filename: return False
            path = Path(filename)
        try:
            saved = self.project_service.save(self.project, path); self.autosave_service.clear(); self.settings.set_value("builder/project_path", str(saved.parent)); self._emit_project(); self.logger.info("Saved Builder project %s", saved); return True
        except BuilderProjectError as exc:
            QMessageBox.critical(self, "Could not save Builder project", str(exc)); return False

    def can_close(self) -> bool:
        return self._maybe_continue()

    def _maybe_continue(self) -> bool:
        if not self.project or not self.project.modified: return True
        answer = QMessageBox.question(self, "Unsaved Builder changes", "Save Template Builder changes before continuing?", QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Save)
        if answer == QMessageBox.StandardButton.Cancel: return False
        if answer == QMessageBox.StandardButton.Save: return self.save_project()
        return True

    def autosave(self) -> None:
        if self.project and self.project.modified:
            try:
                path = self.autosave_service.write(self.project); self.logger.info("Wrote Builder recovery file %s", path)
            except BuilderProjectError as exc: self.logger.exception("Builder autosave failed: %s", exc)

    def _offer_recovery(self) -> None:
        if not self.autosave_service.available(): return
        answer = QMessageBox.question(self, "Recover Template Builder work?", "A Card Studio Template Builder recovery file is available. Recover it now?")
        if answer == QMessageBox.StandardButton.Yes:
            try:
                self.project = self.autosave_service.load(); self.history = HistoryService(60); self.renderer.invalidate(); self._sync_all(); self.generate(); self.logger.info("Loaded Builder recovery data")
            except BuilderProjectError as exc: QMessageBox.critical(self, "Recovery failed", str(exc))
        else: self.autosave_service.clear()

    # ---- sources and transforms -----------------------------------------
    def import_sources(self) -> None:
        if not self.project:
            if not self.new_project(): return
        extensions = " ".join(f"*{suffix}" for suffix in SUPPORTED_SOURCE_FORMATS)
        start = str(self.settings.value("builder/source_path", self.paths.user_data))
        files, _ = QFileDialog.getOpenFileNames(self, "Import same-tier source cards", start, f"Card Images ({extensions})")
        if not files: return
        before = self.project.snapshot(); warnings = []
        for filename in files:
            try:
                loaded = self.source_service.import_source(Path(filename), self.project); self.project.sources.append(loaded.model)
                if self.project.reference_source is None: self.project.set_reference(loaded.model.source_id)
                self.project.selected_source_id = loaded.model.source_id; warnings.extend(f"{loaded.model.label}: {item}" for item in loaded.model.warnings)
            except SourceImportError as exc: warnings.append(str(exc))
        self.history.record(f"Import {len(files)} source card(s)", before, self.project); self.settings.set_value("builder/source_path", str(Path(files[0]).parent)); self._sync_all(); self.generate()
        if warnings: QMessageBox.warning(self, "Source validation", "\n".join(warnings))
        self.logger.info("Imported %s Builder source-card selections", len(files))

    def _selected(self): return self.project.selected_source if self.project else None

    def rename_source(self) -> None:
        source = self._selected()
        if not source: return
        text, ok = QInputDialog.getText(self, "Rename source label", "Display label", text=source.label)
        if ok and text.strip():
            before = self.project.snapshot(); source.label = text.strip(); self.history.record("Rename source", before, self.project); self._sync_all()

    def set_reference(self) -> None:
        source = self._selected()
        if not source: return
        before = self.project.snapshot(); self.project.set_reference(source.source_id); self.history.record("Set reference source", before, self.project); self._sync_all(); self.generate()

    def toggle_source(self) -> None:
        source = self._selected()
        if not source: return
        before = self.project.snapshot(); source.visible = not source.visible; self.history.record("Toggle source visibility", before, self.project); self._sync_all(); self.generate()

    def isolate_source(self) -> None:
        source = self._selected()
        if not source: return
        before = self.project.snapshot(); already = source.isolated
        for item in self.project.sources: item.isolated = False; item.visible = True
        if not already:
            source.isolated = True
            for item in self.project.sources: item.visible = item is source
        self.history.record("Toggle source isolation", before, self.project); self._sync_all(); self.generate()

    def remove_source(self) -> None:
        source = self._selected()
        if not source: return
        if QMessageBox.question(self, "Remove source?", "Remove this reference from the project? The original file will not be deleted.") != QMessageBox.StandardButton.Yes: return
        before = self.project.snapshot(); index = self.project.sources.index(source); self.project.sources.remove(source)
        if source.reference and self.project.sources: self.project.set_reference(self.project.sources[0].source_id)
        self.project.selected_source_id = self.project.sources[min(index, len(self.project.sources)-1)].source_id if self.project.sources else None
        self.history.record("Remove source", before, self.project); self.renderer.invalidate(source.source_id); self._sync_all(); self.generate()

    def move_source(self, delta: int) -> None:
        source = self._selected()
        if not source: return
        old = self.project.sources.index(source); new = max(0, min(len(self.project.sources)-1, old + delta))
        if new == old: return
        before = self.project.snapshot(); self.project.sources.insert(new, self.project.sources.pop(old)); self.history.record("Reorder source priority", before, self.project); self._sync_all(); self.source_list.setCurrentRow(new); self.generate()

    def relink_source(self) -> None:
        source = self._selected()
        if not source: return
        filename, _ = QFileDialog.getOpenFileName(self, "Relink source with matching pixels", str(Path(source.path).parent), "Images (*.png *.webp *.tif *.tiff *.bmp *.jpg *.jpeg)")
        if not filename: return
        try:
            before = self.project.snapshot(); self.source_service.relink(source, Path(filename)); self.history.record("Relink missing source", before, self.project); self._sync_all(); self.generate()
        except SourceImportError as exc: QMessageBox.critical(self, "Relink failed", str(exc))

    def open_source_location(self) -> None:
        source = self._selected()
        if source: QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(source.path).parent)))

    def apply_transform(self) -> None:
        source = self._selected()
        if not source: return
        before = self.project.snapshot(); source.transform.translate_x = self.tx.value(); source.transform.translate_y = self.ty.value(); source.transform.scale = self.scale.value(); source.transform.rotation_degrees = self.rotation.value(); source.transform.subpixel = self.subpixel.isChecked(); source.enabled = True; source.alignment_status = "manual"; source.alignment_method = "manual-subpixel" if source.transform.subpixel else "manual-integer"; self.history.record("Apply source transform", before, self.project); self.renderer.invalidate(source.source_id); self.generate(); self._sync_all()

    def reset_transform(self) -> None:
        source = self._selected()
        if not source: return
        before = self.project.snapshot(); source.transform = SourceTransform(); source.enabled = source.original_width == self.project.width and source.original_height == self.project.height; source.alignment_status = "ready" if source.enabled else "normalization required"; self.history.record("Reset source transform", before, self.project); self.renderer.invalidate(source.source_id); self._sync_all(); self.generate()

    def normalize_source_dialog(self) -> None:
        source = self._selected()
        if not source: return
        try: original = self.source_service.load(source)
        except SourceImportError as exc: QMessageBox.critical(self, "Source missing", str(exc)); return
        dialog = QDialog(self); dialog.setWindowTitle("Non-destructive source normalization"); layout = QVBoxLayout(dialog)
        preview = QLabel(); preview.setAlignment(preview.alignment()); layout.addWidget(preview)
        form = QFormLayout(); perspective = QCheckBox("Use four-corner perspective mapping")
        crop_values = [QDoubleSpinBox() for _ in range(4)]
        defaults = (0, 0, original.width, original.height)
        for widget, value in zip(crop_values, defaults): widget.setRange(-10000, 10000); widget.setValue(value)
        corner_values = [QDoubleSpinBox() for _ in range(8)]
        corners = (0,0, original.width-1,0, original.width-1,original.height-1, 0,original.height-1)
        for widget, value in zip(corner_values, corners): widget.setRange(-10000, 10000); widget.setValue(value)
        form.addRow(perspective); form.addRow("Crop L / T", self._pair(crop_values[0], crop_values[1])); form.addRow("Crop R / B", self._pair(crop_values[2], crop_values[3]))
        for index in range(4): form.addRow(f"Corner {index+1} X / Y", self._pair(corner_values[index*2], corner_values[index*2+1]))
        layout.addLayout(form); update = QPushButton("Preview normalization"); layout.addWidget(update)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel); layout.addWidget(buttons); buttons.accepted.connect(dialog.accept); buttons.rejected.connect(dialog.reject)
        def render_preview():
            try:
                transform = SourceTransform(corners=[(corner_values[i].value(), corner_values[i+1].value()) for i in range(0,8,2)] if perspective.isChecked() else None, crop_rect=None if perspective.isChecked() else tuple(widget.value() for widget in crop_values))
                image = normalize_source(original, (self.project.width, self.project.height), transform); thumb = image.copy(); thumb.thumbnail((260,360)); preview.setPixmap(QPixmap.fromImage(pil_to_qimage(thumb)))
            except ValueError as exc: preview.setText(str(exc))
        update.clicked.connect(render_preview); render_preview()
        if dialog.exec() != QDialog.DialogCode.Accepted: return
        before = self.project.snapshot(); source.transform.corners = [(corner_values[i].value(), corner_values[i+1].value()) for i in range(0,8,2)] if perspective.isChecked() else None; source.transform.crop_rect = None if perspective.isChecked() else tuple(widget.value() for widget in crop_values)
        try: normalize_source(original, (self.project.width, self.project.height), source.transform)
        except ValueError as exc: QMessageBox.critical(self, "Invalid normalization", str(exc)); return
        source.enabled = True; source.alignment_status = "normalized"; source.alignment_method = "four-corner" if perspective.isChecked() else "crop"; self.history.record("Normalize source", before, self.project); self.renderer.invalidate(source.source_id); self._sync_all(); self.generate(); self.logger.info("Normalized Builder source %s", source.label)

    @staticmethod
    def _pair(first, second):
        widget = QWidget(); row = QHBoxLayout(widget); row.setContentsMargins(0,0,0,0); row.addWidget(first); row.addWidget(second); return widget

    def auto_align(self) -> None:
        source, reference = self._selected(), self.project.reference_source if self.project else None
        if not source or not reference or source is reference: QMessageBox.information(self, "Alignment", "Select a non-reference source and set a reference source first."); return
        try:
            fixed = self.renderer.normalized(self.project, reference.source_id); moving = self.renderer.normalized(self.project, source.source_id)
            proposal = propose_alignment(fixed, moving, self.project.masks["alignment"].array(), integer_only=not self.subpixel.isChecked())
        except Exception as exc: QMessageBox.critical(self, "Alignment failed", str(exc)); return
        message = f"Method: {proposal.method}\nX: {proposal.translate_x}\nY: {proposal.translate_y}\nScale: {proposal.scale:.6f}\nRotation: {proposal.rotation_degrees:.4f}°\nConfidence: {proposal.confidence:.3f}"
        if proposal.warning: message += f"\n\nWarning: {proposal.warning}"
        if QMessageBox.question(self, "Accept alignment proposal?", message) != QMessageBox.StandardButton.Yes: return
        before = self.project.snapshot(); source.transform.translate_x += proposal.translate_x; source.transform.translate_y += proposal.translate_y; source.transform.scale *= proposal.scale; source.transform.rotation_degrees += proposal.rotation_degrees; source.transform.subpixel = not proposal.integer_only; source.alignment_status = f"aligned ({proposal.confidence:.2f})"; source.alignment_method = proposal.method; self.history.record("Accept automatic alignment", before, self.project); self.renderer.invalidate(source.source_id); self._sync_all(); self.generate(); self.logger.info("Accepted alignment for %s: %s", source.label, proposal)

    def nudge_source(self, dx: int, dy: int) -> None:
        source = self._selected()
        if not source: return
        before = self.project.snapshot(); source.transform.translate_x += dx; source.transform.translate_y += dy; source.alignment_status = "manual"; self.history.record(f"Nudge source {dx}, {dy}", before, self.project); self.renderer.invalidate(source.source_id); self._sync_transform(); self.generate()

    # ---- analysis and editing -------------------------------------------
    def _apply_composite_settings(self) -> None:
        if not self.project: return
        before = self.project.snapshot()
        self.project.composite_method = self.composite_method.currentText(); self.project.composite_settings.update(trim_fraction=self.trim_fraction.value(), consensus_threshold=self.consensus_threshold.value(), high_threshold=self.high_threshold.value(), medium_threshold=self.medium_threshold.value())
        self.history.record("Change composite settings", before, self.project); self._sync_history()

    def add_region_override(self) -> None:
        if not self.project: return
        before = self.project.snapshot(); mask = self.override_mask.currentText(); method = self.override_method.currentText(); self.project.region_overrides = [item for item in self.project.region_overrides if item.mask_name != mask]; self.project.region_overrides.append(RegionOverride(mask, method)); self.history.record("Set region composite override", before, self.project); self._sync_overrides(); self.generate()

    def generate(self) -> None:
        if not self.project: return
        self.cancel_generation(); self._generation += 1; generation = self._generation
        # Give the worker a detached state snapshot. UI edits can continue and
        # the generation check prevents this result from replacing newer work.
        worker_project = BuilderProject.from_dict(self.project.snapshot(), self.project.file_path.parent if self.project.file_path else None)
        worker = AnalysisWorker(generation, self.renderer, worker_project); self._worker = worker
        worker.signals.result.connect(self._analysis_result); worker.signals.error.connect(self._analysis_error); worker.signals.finished.connect(self._analysis_finished)
        self.progress.show(); self.cancel_button.setEnabled(True); self.generate_button.setEnabled(False); QThreadPool.globalInstance().start(worker); self.logger.info("Started composite generation %s using %s", generation, self.project.composite_method)

    def cancel_generation(self) -> None:
        if self._worker: self._worker.cancelled = True; self._worker = None

    def _analysis_result(self, generation: int, state: BuilderRenderState) -> None:
        if generation != self._generation: return
        self.state = state; self.refresh_view(); self.logger.info("Completed Builder composite generation %s", generation)

    def _analysis_error(self, generation: int, error: str) -> None:
        if generation == self._generation: QMessageBox.critical(self, "Builder analysis failed", error); self.logger.error("Builder worker %s failed: %s", generation, error)

    def _analysis_finished(self, generation: int) -> None:
        if generation == self._generation: self.progress.hide(); self.cancel_button.setEnabled(False); self.generate_button.setEnabled(True); self._worker = None

    def refresh_view(self) -> None:
        if not self.project or not self.state: return
        image = self.renderer.view(self.project, self.state, self.view_mode.currentText(), self.overlay_opacity.value(), self._flicker, self._sample_player); self.canvas.set_image(image)

    def _toggle_flicker(self) -> None:
        self._flicker = not self._flicker
        if self.view_mode.currentText() == "Flicker comparison": self.refresh_view()

    def _edit_started(self) -> None:
        if self.project: self._stroke_before = self.project.snapshot(); self._stroke_points.clear()

    def _brush_points(self, x: int, y: int) -> list[tuple[int,int]]:
        size = self.brush_size.value(); radius = (size - 1) // 2; circular = self.mask_tool.currentText() == "Brush"
        points=[]
        for py in range(y-radius, y+radius+1):
            for px in range(x-radius, x+radius+1):
                if 0 <= px < self.project.width and 0 <= py < self.project.height and (not circular or (px-x)**2+(py-y)**2 <= max(1,radius)**2): points.append((px,py))
        return points or [(x,y)]

    def _edit_point(self, x: int, y: int, right: bool) -> None:
        if not self.project: return
        mode = self.edit_mode.currentText()
        if mode == "Mask":
            mask_name = self.mask_name.currentText(); mask = self.project.masks[mask_name]; tool = self.mask_tool.currentText(); value = 0 if right or tool == "Eraser" else self.mask_alpha.value()
            before_array = mask.array(); protected = self.project.masks["protected"].array() > 0
            if tool == "Flood fill": mask.flood_fill(x,y,value)
            else: mask.apply_brush(x,y,self.brush_size.value(),value,circular=tool not in {"Rectangle"})
            if mask_name != "protected" and np.any(protected):
                after = mask.array(); after[protected] = before_array[protected]; mask.set_array(after)
        elif mode == "Source patch":
            protected = self.project.masks["protected"].array()
            for point in self._brush_points(x,y):
                if protected[point[1], point[0]] == 0: self._stroke_points.add(point)
        else:
            protected = self.project.masks["protected"].array()
            for px,py in self._brush_points(x,y):
                if protected[py,px] > 0: continue
                key=f"{px},{py}"
                if right: self.project.manual_pixels.pop(key,None)
                else: self.project.manual_pixels[key]=list(self._manual_rgba)

    def _edit_rectangle(self, x1: int, y1: int, x2: int, y2: int, right: bool) -> None:
        if not self.project: return
        box=(min(x1,x2),min(y1,y2),max(x1,x2),max(y1,y2)); mode=self.edit_mode.currentText()
        if mode == "Mask":
            mask_name=self.mask_name.currentText(); mask=self.project.masks[mask_name]; value=0 if right else self.mask_alpha.value(); before_array=mask.array(); protected=self.project.masks["protected"].array()>0
            (mask.ellipse if self.mask_tool.currentText()=="Ellipse" else mask.rectangle)(box,value)
            if mask_name != "protected" and np.any(protected):
                after=mask.array(); after[protected]=before_array[protected]; mask.set_array(after)
        else:
            protected=self.project.masks["protected"].array()
            for y in range(box[1],box[3]+1):
                for x in range(box[0],box[2]+1):
                    if protected[y,x] > 0: continue
                    if mode == "Manual pixel":
                        key=f"{x},{y}"
                        if right: self.project.manual_pixels.pop(key,None)
                        else: self.project.manual_pixels[key]=list(self._manual_rgba)
                    else: self._stroke_points.add((x,y))

    def _edit_finished(self) -> None:
        if not self.project or self._stroke_before is None: return
        mode=self.edit_mode.currentText()
        if mode == "Source patch" and self._stroke_points:
            source=self._selected()
            if source:
                ox=self.offset_x.value() if self.offset_patch.isChecked() else 0; oy=self.offset_y.value() if self.offset_patch.isChecked() else 0
                self.project.patches.append(PatchOperation(source.source_id,sorted(self._stroke_points),ox,oy,"brush"))
        description={"Mask":"Edit mask","Source patch":"Apply authentic source patch","Manual pixel":"Edit manual pixels"}[mode]
        self.history.record(description,self._stroke_before,self.project); self._stroke_before=None; self._sync_history(); self.generate()

    def _mask_action(self, action: str) -> None:
        if not self.project: return
        before=self.project.snapshot(); mask=self.project.masks[self.mask_name.currentText()]; getattr(mask,action)(); self.history.record(f"{action.title()} {mask.name} mask",before,self.project); self._sync_history(); self.generate()

    def choose_manual_color(self) -> None:
        current=QColor(*self._manual_rgba); color=QColorDialog.getColor(current,self,"Manual RGBA pixel",QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid(): self._manual_rgba=[color.red(),color.green(),color.blue(),color.alpha()]; self.pixel_color.setText(f"Manual RGBA: {','.join(map(str,self._manual_rgba))}")

    def pick_pixel(self, source_name: str) -> None:
        if not self.project or not self.state or self._cursor_xy is None: return
        values=self.renderer.pixel_readout(self.project,self.state,*self._cursor_xy); value=values.get(source_name)
        if value is not None:
            self._manual_rgba=list(value); self.pixel_color.setText(f"Manual RGBA: {','.join(map(str,self._manual_rgba))}")

    def feather_mask(self) -> None:
        if not self.project: return
        before=self.project.snapshot(); mask=self.project.masks[self.mask_name.currentText()]; mask.apply_feather(self.feather_amount.value()); self.history.record(f"Feather {mask.name} mask",before,self.project); self._sync_history(); self.generate()

    def polygon_mask(self) -> None:
        if not self.project: return
        text,ok=QInputDialog.getMultiLineText(self,"Polygon mask","Enter one native-coordinate point per line as x,y:","0,0\n10,0\n10,10\n0,10")
        if not ok: return
        try:
            points=[tuple(int(value.strip()) for value in line.split(",",1)) for line in text.splitlines() if line.strip()]
            before=self.project.snapshot(); self.project.masks[self.mask_name.currentText()].polygon(points,self.mask_alpha.value()); self.history.record("Fill polygon mask",before,self.project); self._sync_history(); self.generate()
        except (ValueError,TypeError) as exc: QMessageBox.warning(self,"Invalid polygon",str(exc))

    # ---- text, history, finalization ------------------------------------
    def save_text_region(self) -> None:
        if not self.project: return
        before=self.project.snapshot(); region=self.project.text_regions[self.text_field.currentText()]; region.x=self.text_x.value(); region.y=self.text_y.value(); region.width=self.text_w.value(); region.height=self.text_h.value(); region.baseline=None if self.text_baseline.value()<0 else self.text_baseline.value(); region.maximum_width=self.text_max_width.value(); region.horizontal_alignment=self.text_halign.currentText(); region.vertical_alignment=self.text_valign.currentText(); region.clean=self.text_clean.isChecked(); region.expected_color=list(self._text_rgba); region.notes=self.text_notes.toPlainText(); region.reference_source_id=self.project.reference_source.source_id if self.project.reference_source else None; self.history.record(f"Update {region.field_id} text region",before,self.project); self._sync_history()

    def choose_text_color(self) -> None:
        color = QColorDialog.getColor(QColor(*self._text_rgba), self, "Expected text-region color", QColorDialog.ColorDialogOption.ShowAlphaChannel)
        if color.isValid():
            self._text_rgba = [color.red(), color.green(), color.blue(), color.alpha()]
            self.text_color.setText(f"Expected RGBA: {','.join(map(str, self._text_rgba))}")

    def _set_autosave_interval(self, minutes: int) -> None:
        self.settings.set_value("builder/autosave_minutes", int(minutes))
        self._autosave_timer.setInterval(max(1, int(minutes)) * 60_000)

    def undo(self) -> None:
        if not self.project or not self.history.can_undo: return
        self.project=self.history.undo(self.project); self.renderer.invalidate(); self._sync_all(); self.generate()

    def redo(self) -> None:
        if not self.project or not self.history.can_redo: return
        self.project=self.history.redo(self.project); self.renderer.invalidate(); self._sync_all(); self.generate()

    def load_sample_player(self) -> None:
        filename,_=QFileDialog.getOpenFileName(self,"Load temporary sample player",str(self.paths.user_data),"PNG/WebP (*.png *.webp)")
        if filename:
            with Image.open(filename) as opened: self._sample_player=opened.convert("RGBA").copy()
            if self.project: self.project.sample_player_path=filename
            self.view_mode.setCurrentText("Final layer preview"); self.refresh_view()

    def show_validation(self) -> None:
        if not self.project or not self.state: return
        report=self.export_service.validate(self.project,self.state); text=[]
        text.extend(f"ERROR: {item}" for item in report.errors); text.extend(f"WARNING: {item}" for item in report.warnings)
        if not text: text=["Ready to export. No structural errors or warnings detected."]
        self.final_report.setPlainText("\n".join(text))

    def export_template(self) -> None:
        if not self.project or not self.state: return
        self.show_validation(); report=self.export_service.validate(self.project,self.state)
        if report.errors: QMessageBox.critical(self,"Export blocked","\n".join(report.errors)); return
        if report.warnings and QMessageBox.warning(self,"Export warnings","\n".join(report.warnings)+"\n\nExport anyway?",QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,QMessageBox.StandardButton.No)!=QMessageBox.StandardButton.Yes: return
        directory=QFileDialog.getExistingDirectory(self,"Choose template output root",str(self.paths.templates))
        if not directory: return
        try:
            target=self.export_service.export(self.project,self.state,Path(directory),allow_warnings=True); self.final_report.append(f"\nExported: {target}"); self.template_exported.emit(str(target)); self.logger.info("Exported Builder template package %s",target)
        except TemplateExportError as exc: QMessageBox.critical(self,"Export failed",str(exc))

    # ---- synchronization -------------------------------------------------
    def _sync_all(self) -> None:
        self._sync_sources(); self._sync_transform(); self._sync_composite(); self._sync_masks(); self._sync_overrides(); self._sync_history(); self._load_text_region(); self._emit_project()

    def _sync_composite(self) -> None:
        if not self.project: return
        widgets=((self.composite_method,self.project.composite_method),(self.trim_fraction,float(self.project.composite_settings.get("trim_fraction",.2))),(self.consensus_threshold,float(self.project.composite_settings.get("consensus_threshold",.75))),(self.high_threshold,float(self.project.composite_settings.get("high_threshold",.9))),(self.medium_threshold,float(self.project.composite_settings.get("medium_threshold",.65))))
        for widget,value in widgets:
            widget.blockSignals(True)
            if isinstance(widget,QComboBox): widget.setCurrentText(str(value))
            else: widget.setValue(value)
            widget.blockSignals(False)

    def _sync_sources(self) -> None:
        self.source_list.blockSignals(True); self.source_list.clear()
        if self.project:
            for source in self.project.sources:
                flags=("★ " if source.reference else "")+("◉ " if source.visible else "○ ")
                item=QListWidgetItem(flags+source.label); item.setToolTip("\n".join(source.warnings))
                try: item.setIcon(QIcon(QPixmap.fromImage(pil_to_qimage(self.source_service.thumbnail(source)))))
                except (OSError, SourceImportError): pass
                self.source_list.addItem(item)
            if self.project.selected_source:
                self.source_list.setCurrentRow(self.project.sources.index(self.project.selected_source))
        self.source_list.blockSignals(False); self._source_selected(self.source_list.currentRow())

    def _source_selected(self, row: int) -> None:
        if not self.project or not 0<=row<len(self.project.sources): self.source_info.setText("No source selected"); return
        source=self.project.sources[row]; self.project.selected_source_id=source.source_id
        warning="; ".join(source.warnings) or "None"
        self.source_info.setText(f"{source.original_width} × {source.original_height} | {source.color_mode} | alpha: {'yes' if source.has_alpha else 'no'}\nStatus: {source.alignment_status}\nWarnings: {warning}")
        self._sync_transform(); self.refresh_view()

    def _sync_transform(self) -> None:
        source=self._selected()
        if not source: return
        for widget,value in ((self.tx,source.transform.translate_x),(self.ty,source.transform.translate_y),(self.scale,source.transform.scale),(self.rotation,source.transform.rotation_degrees)): widget.blockSignals(True); widget.setValue(value); widget.blockSignals(False)
        self.subpixel.setChecked(source.transform.subpixel)

    def _sync_masks(self) -> None:
        if not self.project: return
        selected=self.mask_name.currentText();
        if not self.keep_masks_visible.isChecked():
            for mask in self.project.masks.values(): mask.visible=False
        self.project.masks[selected].visible=self.mask_visible.isChecked()

    def _mask_selection_changed(self) -> None:
        self._sync_masks(); self.refresh_view()

    def _mask_visibility_changed(self, value: bool) -> None:
        if self.project: self.project.masks[self.mask_name.currentText()].visible=value; self.refresh_view()

    def _tool_changed(self, text: str) -> None:
        self.canvas.edit_shape="rectangle" if text=="Rectangle" else "ellipse" if text=="Ellipse" else "brush"

    def _sync_overrides(self) -> None:
        self.override_list.clear()
        if self.project:
            for item in self.project.region_overrides: self.override_list.addItem(f"{item.mask_name}: {item.method}")

    def _sync_history(self) -> None:
        self.history_list.clear(); self.history_list.addItems(self.history.descriptions()); self.undo_button.setEnabled(self.history.can_undo); self.redo_button.setEnabled(self.history.can_redo)

    def _load_text_region(self) -> None:
        if not self.project: return
        region=self.project.text_regions[self.text_field.currentText()]
        for widget,value in ((self.text_x,region.x),(self.text_y,region.y),(self.text_w,region.width),(self.text_h,region.height),(self.text_baseline,-1 if region.baseline is None else region.baseline),(self.text_max_width,region.maximum_width)): widget.setValue(value)
        self.text_halign.setCurrentText(region.horizontal_alignment); self.text_valign.setCurrentText(region.vertical_alignment); self.text_clean.setChecked(region.clean); self.text_notes.setPlainText(region.notes)
        self._text_rgba = list(region.expected_color); self.text_color.setText(f"Expected RGBA: {','.join(map(str, self._text_rgba))}")

    def _pixel_moved(self, x: int, y: int) -> None:
        if not self.project or not self.state: return
        self._cursor_xy=(x,y)
        values=self.renderer.pixel_readout(self.project,self.state,x,y); fmt=lambda value: "—" if value is None else str(tuple(value))
        self.pixel_status.setText(f"Pixel: {x}, {y} | Reference: {fmt(values['reference'])} | Selected: {fmt(values['selected'])} | Candidate: {fmt(values['candidate'])} | Final: {fmt(values['final'])}")

    def _emit_project(self) -> None:
        name=self.project.file_path.name if self.project and self.project.file_path else (f"{self.project.template_id}{BUILDER_PROJECT_EXTENSION}" if self.project else "No Builder project")
        modified=bool(self.project and self.project.modified); self.project_changed.emit(name,modified)
