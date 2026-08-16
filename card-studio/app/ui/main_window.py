"""Single-workspace Card Studio window focused on the normal card workflow."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from app.constants import APPLICATION_NAME
from app.ui.canvas_widget import CardCanvasWidget
from app.ui.player_controls import PlayerControls
from app.ui.player_data_editor import PlayerDataEditor


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APPLICATION_NAME)
        self.resize(1120, 820)
        self.close_guard: Callable[[], bool] | None = None
        self.canvas = CardCanvasWidget()
        self.player_controls = PlayerControls()
        self._create_actions()
        self._create_workspace()
        self._create_menus()
        self.statusBar().showMessage("Ready")
        self.setStyleSheet(
            """
            QMainWindow, QWidget { background: #151b24; color: #e5ebf3; }
            QMenuBar, QMenu { background: #111720; color: #e5ebf3; }
            QGroupBox { border: 1px solid #344257; border-radius: 6px; margin-top: 10px; padding: 9px; font-weight: 600; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 4px; }
            QPushButton { background: #26364a; border: 1px solid #49617f; border-radius: 4px; padding: 8px 12px; }
            QPushButton:hover { background: #304761; }
            QPushButton:disabled { background: #1b2532; color: #667387; border-color: #2d3b4d; }
            QPushButton#primaryButton { background: #176b78; border-color: #43b7c5; font-weight: 700; }
            QPushButton#primaryButton:hover { background: #208393; }
            QDoubleSpinBox, QComboBox, QLineEdit { background: #0e141c; border: 1px solid #3c4b60; padding: 6px; }
            QStatusBar { background: #0d1219; color: #b6c3d3; }
            """
        )

    def _create_actions(self) -> None:
        self.new_action = QAction("New Project", self, shortcut=QKeySequence.StandardKey.New)
        self.open_action = QAction("Open Project", self, shortcut=QKeySequence.StandardKey.Open)
        self.save_action = QAction("Save Project", self, shortcut=QKeySequence.StandardKey.Save)
        self.import_action = QAction("Import Player Image", self, shortcut="Ctrl+I")
        self.remove_background_action = QAction("Remove Background", self, shortcut="Ctrl+Shift+R")
        self.remove_background_action.setEnabled(False)
        self.delete_image_action = QAction("Delete PNG", self)
        self.delete_image_action.setEnabled(False)
        self.export_action = QAction("Export PNG", self, shortcut="Ctrl+E")
        self.export_custom_action = QAction("Export Card + Data", self, shortcut="Ctrl+Shift+E")
        self.edit_attributes_action = QAction("Edit Attributes", self)
        self.exit_action = QAction("Exit", self, shortcut=QKeySequence.StandardKey.Quit)
        self.undo_action = QAction("Undo", self, shortcut=QKeySequence.StandardKey.Undo)
        self.redo_action = QAction("Redo", self, shortcut=QKeySequence.StandardKey.Redo)
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)
        self.about_action = QAction("About", self)
        self.readme_action = QAction("Usage Instructions", self, shortcut=QKeySequence.StandardKey.HelpContents)

    def _create_workspace(self) -> None:
        workspace = QWidget()
        layout = QVBoxLayout(workspace)
        layout.setContentsMargins(10, 8, 10, 8)

        workflow = QGroupBox("Create Card")
        workflow_layout = QGridLayout(workflow)
        workflow_layout.addWidget(QLabel("Card tier"), 0, 0)
        self.template_combo = QComboBox()
        self.template_combo.setMinimumWidth(210)
        workflow_layout.addWidget(self.template_combo, 0, 1, 1, 2)
        workflow_layout.addWidget(QLabel("Player size"), 0, 3)
        self.player_size = QDoubleSpinBox()
        self.player_size.setObjectName("playerSizeInput")
        self.player_size.setRange(5.0, 500.0)
        self.player_size.setDecimals(2)
        self.player_size.setSingleStep(0.25)
        self.player_size.setSuffix(" %")
        self.player_size.setValue(100.0)
        self.player_size.setKeyboardTracking(False)
        self.player_size.setToolTip("Exact imported-player size. Ctrl+mouse-wheel changes this gradually.")
        workflow_layout.addWidget(self.player_size, 0, 4)
        self.project_summary = QLabel("Untitled project")
        self.project_summary.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        workflow_layout.addWidget(self.project_summary, 0, 5, 1, 2)
        edit_attributes = QPushButton("Edit Attributes")
        edit_attributes.setObjectName("editAttributesButton")
        edit_attributes.clicked.connect(self.edit_attributes_action.trigger)
        workflow_layout.addWidget(edit_attributes, 0, 7)

        workflow_layout.addWidget(QLabel("Logo set"), 1, 0)
        self.logo_category_combo = QComboBox()
        self.logo_category_combo.setObjectName("logoCategoryCombo")
        self.logo_category_combo.setMinimumWidth(115)
        workflow_layout.addWidget(self.logo_category_combo, 1, 1)
        workflow_layout.addWidget(QLabel("Team logo"), 1, 2)
        self.logo_combo = QComboBox()
        self.logo_combo.setObjectName("logoCombo")
        self.logo_combo.setMinimumWidth(245)
        workflow_layout.addWidget(self.logo_combo, 1, 3, 1, 2)

        workflow_layout.addWidget(QLabel("Card background"), 2, 0)
        self.background_combo = QComboBox()
        self.background_combo.setObjectName("backgroundCombo")
        self.background_combo.setMinimumWidth(245)
        self.background_combo.addItem("No background", "")
        workflow_layout.addWidget(self.background_combo, 2, 1, 1, 2)
        workflow_layout.addWidget(QLabel("Promotion logo"), 2, 3)
        self.promotion_combo = QComboBox()
        self.promotion_combo.setObjectName("promotionCombo")
        self.promotion_combo.setMinimumWidth(245)
        self.promotion_combo.addItem("No promotion logo", "")
        workflow_layout.addWidget(self.promotion_combo, 2, 4, 1, 3)

        buttons = (
            ("Import Image", self.import_action, "importButton"),
            ("Remove Background", self.remove_background_action, "removeBackgroundButton"),
            ("Delete PNG", self.delete_image_action, "deleteButton"),
            ("Open Project", self.open_action, "openButton"),
            ("Save Project", self.save_action, "saveButton"),
            ("Export PNG", self.export_action, "primaryButton"),
            ("Export Card + Data", self.export_custom_action, "exportCustomButton"),
            ("Undo", self.undo_action, "undoButton"),
            ("Redo", self.redo_action, "redoButton"),
        )
        self.workflow_buttons: dict[str, QPushButton] = {}
        for column, (label, action, object_name) in enumerate(buttons):
            button = QPushButton(label)
            button.setObjectName(object_name)
            button.clicked.connect(action.trigger)
            button.setEnabled(action.isEnabled())
            action.changed.connect(lambda a=action, b=button: b.setEnabled(a.isEnabled()))
            workflow_layout.addWidget(button, 3, column)
            self.workflow_buttons[object_name] = button
        workflow_layout.setColumnStretch(8, 1)
        layout.addWidget(workflow)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self.canvas)
        splitter.addWidget(self.player_controls)
        splitter.setSizes([830, 260])
        splitter.setStretchFactor(0, 1)
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        layout.addWidget(splitter, 1)
        self.card_workspace = workspace
        self.player_data_editor = PlayerDataEditor()
        self.workspace_stack = QStackedWidget()
        self.workspace_stack.addWidget(self.card_workspace)
        self.workspace_stack.addWidget(self.player_data_editor)
        self.setCentralWidget(self.workspace_stack)

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        for action in (
            self.new_action,
            self.open_action,
            self.save_action,
            self.import_action,
            self.remove_background_action,
            self.delete_image_action,
            self.export_action,
            self.export_custom_action,
            self.exit_action,
        ):
            file_menu.addAction(action)

        edit_menu = self.menuBar().addMenu("Edit")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.readme_action)
        help_menu.addAction(self.about_action)

    def show_player_data_editor(self, player_data: dict) -> None:
        self.player_data_editor.set_player_data(player_data)
        self.workspace_stack.setCurrentWidget(self.player_data_editor)

    def show_card_editor(self) -> None:
        self.workspace_stack.setCurrentWidget(self.card_workspace)

    def set_template_choices(self, choices: list[tuple[str, Path]]) -> None:
        self.template_combo.blockSignals(True)
        self.template_combo.clear()
        for label, path in choices:
            self.template_combo.addItem(label, str(path.resolve()))
        self.template_combo.blockSignals(False)

    def set_logo_categories(self, choices: list[tuple[str, str]]) -> None:
        self.logo_category_combo.blockSignals(True)
        self.logo_category_combo.clear()
        for label, category_id in choices:
            self.logo_category_combo.addItem(label, category_id)
        self.logo_category_combo.blockSignals(False)

    def set_logo_choices(self, choices: list[tuple[str, str]], selected_id: str = "") -> None:
        self.logo_combo.blockSignals(True)
        self.logo_combo.clear()
        self.logo_combo.addItem("No logo", "")
        for label, asset_id in choices:
            self.logo_combo.addItem(label, asset_id)
        wanted = str(selected_id or "")
        index = self.logo_combo.findData(wanted)
        self.logo_combo.setCurrentIndex(max(0, index))
        self.logo_combo.blockSignals(False)

    def set_logo_state(self, category: str, asset_id: str) -> None:
        self.logo_category_combo.blockSignals(True)
        category_index = self.logo_category_combo.findData(category)
        self.logo_category_combo.setCurrentIndex(max(0, category_index))
        self.logo_category_combo.blockSignals(False)
        self.logo_combo.blockSignals(True)
        logo_index = self.logo_combo.findData(asset_id)
        self.logo_combo.setCurrentIndex(max(0, logo_index))
        self.logo_combo.blockSignals(False)

    def set_background_choices(self, choices: list[tuple[str, str]]) -> None:
        self.background_combo.blockSignals(True)
        self.background_combo.clear()
        self.background_combo.addItem("No background", "")
        for label, asset_id in choices:
            self.background_combo.addItem(label, asset_id)
        self.background_combo.blockSignals(False)

    def set_promotion_choices(self, choices: list[tuple[str, str]]) -> None:
        self.promotion_combo.blockSignals(True)
        self.promotion_combo.clear()
        self.promotion_combo.addItem("No promotion logo", "")
        for label, asset_id in choices:
            self.promotion_combo.addItem(label, asset_id)
        self.promotion_combo.blockSignals(False)

    def set_background_selection(self, asset_id: str) -> None:
        self.background_combo.blockSignals(True)
        self.background_combo.setCurrentIndex(max(0, self.background_combo.findData(asset_id)))
        self.background_combo.blockSignals(False)

    def set_promotion_selection(self, asset_id: str) -> None:
        self.promotion_combo.blockSignals(True)
        self.promotion_combo.setCurrentIndex(max(0, self.promotion_combo.findData(asset_id)))
        self.promotion_combo.blockSignals(False)

    def set_player_size_percent(self, value: float) -> None:
        """Synchronize the precise size field without creating an edit signal."""
        self.player_size.blockSignals(True)
        self.player_size.setValue(value)
        self.player_size.blockSignals(False)

    def select_template_path(self, path: Path) -> None:
        wanted = str(path.resolve())
        self.template_combo.blockSignals(True)
        for index in range(self.template_combo.count()):
            if str(Path(str(self.template_combo.itemData(index))).resolve()) == wanted:
                self.template_combo.setCurrentIndex(index)
                break
        self.template_combo.blockSignals(False)

    def set_project_title(self, filename: str, modified: bool) -> None:
        marker = " *" if modified else ""
        self.setWindowTitle(f"{filename}{marker} — {APPLICATION_NAME}")

    def update_project_summary(self, filename: str, template_name: str, size: tuple[int, int], modified: bool) -> None:
        marker = " • unsaved" if modified else ""
        self.project_summary.setText(f"{filename}{marker}  |  {template_name}  |  {size[0]} × {size[1]}")

    def set_status(self, text: str) -> None:
        self.statusBar().showMessage(text)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt API
        if self.close_guard is not None and not self.close_guard():
            event.ignore()
            return
        event.accept()
