"""Application controller connecting independent services, renderer, and UI."""

from __future__ import annotations

import logging
import re
import threading
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox

from app.constants import APPLICATION_NAME, APPLICATION_VERSION, DEFAULT_TEMPLATE_ID, PROJECT_EXTENSION
from app.background_removal.cutout_service import apply_alpha_mask, decode_mask_png, encode_mask_png
from app.background_removal.inference_service import BackgroundRemovalInferenceService
from app.background_removal.mask_postprocessing import MaskPostprocessSettings
from app.background_removal.model_manager import BackgroundRemovalModelManager
from app.background_removal.worker import BackgroundRemovalWorker
from app.models.logo_model import LogoPlacement
from app.models.card_assets_model import CardAssetSelection
from app.models.player_art_model import PlayerTransform
from app.models.project_model import CardProject, TemplateReference
from app.models.template_model import CardTemplate
from app.rendering.card_renderer import CardRenderer
from app.rendering.export_service import ExportService
from app.rendering.image_loader import LoadedPlayerImage, load_player_image
from app.services.project_service import ProjectService
from app.services.custom_card_service import CUSTOM_CARD_EXTENSION, CustomCardService
from app.services.card_asset_service import BACKGROUND_DISPLAY_NAMES, PngCardAssetService, promotion_display_names
from app.services.logo_service import LOGO_CATEGORIES, LogoService
from app.services.settings_service import SettingsService
from app.services.template_service import TemplateService
from app.player_data.preset_database import PlayerPresetDatabase
from app.player_data.promotion_taxonomy import apply_promotion_taxonomy
from app.text.normalization import normalize_name, normalize_overall, normalize_position
from app.ui.dialogs import show_error, show_information
from app.ui.background_removal_dialog import BackgroundRemovalDialog
from app.ui.background_removal_progress_dialog import BackgroundRemovalProgressDialog
from app.ui.main_window import MainWindow
from app.utilities.paths import AppPaths, background_removal_model_root
from app.utilities.validation import CardStudioError, TemplateValidationError


class CardStudioApplication:
    """High-level workflow controller; rendering remains fully UI-independent."""

    def __init__(self, qt_app: QApplication, paths: AppPaths, logger: logging.Logger) -> None:
        self.qt_app = qt_app
        self.paths = paths
        self.logger = logger
        self.settings = SettingsService()
        self.template_service = TemplateService(paths.templates)
        self.logo_service = LogoService(paths.root / "assets" / "team_logos")
        promotion_root = paths.root / "assets" / "myteam_promotion_logos" / "runtime" / "normalized"
        self.background_service = PngCardAssetService(
            paths.root / "assets" / "myteam_card_backgrounds" / "png", BACKGROUND_DISPLAY_NAMES
        )
        self.promotion_service = PngCardAssetService(
            promotion_root, promotion_display_names(promotion_root)
        )
        self.project_service = ProjectService()
        self.renderer = CardRenderer(paths.root / "assets" / "text_styles")
        self.window = MainWindow()
        self.window.player_data_editor.set_preset_database(
            PlayerPresetDatabase.load(paths.root / "assets" / "player_database" / "player_presets.json")
        )
        self.template: CardTemplate | None = None
        self.project: CardProject | None = None
        self.player_source: LoadedPlayerImage | None = None
        self.original_player_source: LoadedPlayerImage | None = None
        self.background_removal_service: BackgroundRemovalInferenceService | None = None
        self._background_request_id = 0
        self._background_cancel = threading.Event()
        self._background_progress: BackgroundRemovalProgressDialog | None = None
        self._last_inference_seconds: float | None = None
        self.logo_image = None
        self.background_image = None
        self.promotion_image = None
        self._history: list[dict] = []
        self._history_index = -1
        self._restoring_history = False
        self._connect_ui()
        self._populate_template_selector()
        self._populate_logo_categories()
        self._populate_card_assets()
        self._restore_window()
        self.new_project(force=True)

    def show(self) -> None:
        self.window.show()

    def _connect_ui(self) -> None:
        w = self.window
        w.new_action.triggered.connect(self.new_project)
        w.open_action.triggered.connect(self.open_project)
        w.save_action.triggered.connect(self.save_project)
        w.import_action.triggered.connect(self.import_player_image)
        w.remove_background_action.triggered.connect(self.remove_background)
        w.delete_image_action.triggered.connect(self.delete_player_image)
        w.export_action.triggered.connect(self.export_png)
        w.export_custom_action.triggered.connect(self.export_custom_card)
        w.edit_attributes_action.triggered.connect(self.edit_player_data)
        w.player_data_editor.done_requested.connect(self.finish_player_data)
        w.exit_action.triggered.connect(w.close)
        w.about_action.triggered.connect(self.show_about)
        w.readme_action.triggered.connect(self.open_readme)
        w.undo_action.triggered.connect(self.undo)
        w.redo_action.triggered.connect(self.redo)
        w.template_combo.currentIndexChanged.connect(self._template_selection_changed)
        w.logo_category_combo.currentIndexChanged.connect(self._logo_category_changed)
        w.logo_combo.currentIndexChanged.connect(self._logo_selection_changed)
        w.background_combo.currentIndexChanged.connect(self._background_selection_changed)
        w.promotion_combo.currentIndexChanged.connect(self._promotion_selection_changed)
        w.player_size.valueChanged.connect(self.set_player_scale_percent)
        w.player_controls.transform_changed.connect(self.set_transform)
        w.player_controls.text_changed.connect(self.set_text_fields)
        w.canvas.player_moved.connect(self.move_player)
        w.canvas.nudge_requested.connect(self.nudge_player)
        w.canvas.player_scale_requested.connect(self.scale_player)
        w.canvas.player_delete_requested.connect(self.delete_player_image)
        w.canvas.zoom_changed.connect(self._zoom_changed)
        w.close_guard = self.can_close

    def new_project(self, force: bool = False) -> None:
        if not force and not self._maybe_continue():
            return
        try:
            template_id = str(self.settings.value("template/last", DEFAULT_TEMPLATE_ID))
            template_path = str(self.settings.value("template/last_path", ""))
            try:
                saved_path = Path(template_path).resolve() if template_path and Path(template_path).is_dir() else None
                installed = {path.resolve() for path in self.template_service.discover()}
                self.template = self.template_service.load(saved_path if saved_path in installed else template_id)
            except TemplateValidationError:
                self.template = self.template_service.load(DEFAULT_TEMPLATE_ID)
            defaults = self.template.player_defaults
            self.project = CardProject(
                template=TemplateReference(self.template.template_id, str(self.template.directory)),
                player_source_path=None,
                player_transform=PlayerTransform(
                    defaults.anchor_x,
                    defaults.anchor_y,
                    defaults.scale,
                    defaults.rotation_degrees,
                    defaults.flip_horizontal,
                ),
                logo=LogoPlacement(
                    category="current",
                    asset_id="",
                ),
                card_assets=CardAssetSelection(),
            )
            self._cancel_background_removal()
            self.player_source = None
            self.original_player_source = None
            self.logo_image = None
            self.background_image = None
            self.promotion_image = None
            self.window.player_controls.clear_source_info()
            self._sync_ui()
            self._reset_history()
            self.logger.info("Created new project with template %s", self.template.template_id)
        except CardStudioError as exc:
            self._report_error("Could not create project", exc)

    def open_project(self) -> None:
        if not self._maybe_continue():
            return
        start = str(self.settings.value("paths/project", self.paths.projects))
        filename, _ = QFileDialog.getOpenFileName(
            self.window, "Open Card Studio Project", start, f"Card Studio Projects (*{PROJECT_EXTENSION})"
        )
        if not filename:
            return
        try:
            project = self.project_service.load(Path(filename))
            self.template = self._load_project_template(project)
            self.project = project
            missing = self.project_service.missing_player_path(project)
            self._cancel_background_removal()
            self.player_source = None
            self.original_player_source = None
            if missing is not None:
                answer = QMessageBox.question(
                    self.window,
                    "Player image missing",
                    f"The referenced player image was not found:\n{missing}\n\nLocate it now?",
                )
                if answer == QMessageBox.StandardButton.Yes:
                    located, _ = QFileDialog.getOpenFileName(self.window, "Locate Player Image", str(missing.parent), self._image_filter())
                    if located:
                        project.player_source_path = str(Path(located).resolve())
            if project.player_source_path and Path(project.player_source_path).is_file():
                self.original_player_source = load_player_image(Path(project.player_source_path))
                self.player_source = self._source_with_saved_mask(project, self.original_player_source)
            self.logo_image = self._load_project_logo(project)
            self.background_image = self._load_project_card_asset(
                self.background_service, project.card_assets.background_id, "background"
            )
            self.promotion_image = self._load_project_card_asset(
                self.promotion_service, project.card_assets.promotion_logo_id, "promotion logo"
            )
            self.settings.set_value("paths/project", str(Path(filename).parent))
            self._sync_ui()
            self._reset_history()
            self.logger.info("Opened project %s", filename)
        except CardStudioError as exc:
            self._report_error("Could not open project", exc)

    def save_project(self, save_as: bool = False) -> bool:
        if self.project is None:
            return False
        path = self.project.file_path
        if save_as or path is None:
            start = path or Path(str(self.settings.value("paths/project", self.paths.projects))) / "untitled.2k16card"
            filename, _ = QFileDialog.getSaveFileName(
                self.window, "Save Card Studio Project", str(start), f"Card Studio Projects (*{PROJECT_EXTENSION})"
            )
            if not filename:
                return False
            path = Path(filename)
            if path.suffix.lower() != PROJECT_EXTENSION:
                path = path.with_suffix(PROJECT_EXTENSION)
        try:
            self.project_service.save(self.project, path)
            self.settings.set_value("paths/project", str(path.parent))
            self._sync_project_labels()
            self._replace_current_history()
            self._set_status(f"Saved project: {path}")
            self.logger.info("Saved project %s", path)
            return True
        except CardStudioError as exc:
            self._report_error("Could not save project", exc)
            return False

    def import_player_image(self) -> None:
        start = str(self.settings.value("paths/import", self.paths.user_data))
        filename, _ = QFileDialog.getOpenFileName(self.window, "Import Player Image", start, self._image_filter())
        if not filename:
            return
        try:
            self._cancel_background_removal()
            loaded = load_player_image(Path(filename))
            self.player_source = loaded
            self.original_player_source = loaded
            assert self.project is not None
            self.project.player_source_path = str(loaded.source_path)
            self.project.background_removal = self.project.background_removal.__class__()
            self.project.modified = True
            self.window.player_controls.set_source_info(*loaded.original_size, loaded.has_transparency)
            self.settings.set_value("paths/import", str(loaded.source_path.parent))
            self._sync_ui()
            self._push_history()
            self.logger.info("Imported player image %s (%sx%s)", loaded.source_path, *loaded.original_size)
            if not loaded.has_transparency:
                self._offer_background_removal()
        except CardStudioError as exc:
            self._report_error("Could not import player image", exc)

    def _offer_background_removal(self) -> None:
        dialog = QMessageBox(self.window)
        dialog.setWindowTitle("Player Image Background")
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText("This image does not contain transparency.")
        dialog.setInformativeText(
            "Keep the original background, or create a transparent cutout with the packaged local model?"
        )
        keep = dialog.addButton("Keep Original Background", QMessageBox.ButtonRole.RejectRole)
        remove = dialog.addButton("Remove Background", QMessageBox.ButtonRole.AcceptRole)
        dialog.setDefaultButton(remove)
        dialog.exec()
        if dialog.clickedButton() is remove:
            QTimer.singleShot(0, self.remove_background)
        else:
            dialog.setDefaultButton(keep)

    def remove_background(self) -> None:
        if self.project is None or self.original_player_source is None:
            return
        state = self.project.background_removal
        settings = MaskPostprocessSettings.from_dict(state.postprocessing)
        if state.enabled and state.automatic_mask_png:
            try:
                automatic = decode_mask_png(
                    state.automatic_mask_png, self.original_player_source.original_size
                )
                current = decode_mask_png(
                    state.accepted_mask_png, self.original_player_source.original_size
                )
                self._show_background_result(automatic, settings, current)
                return
            except CardStudioError as exc:
                self.logger.warning("Saved mask could not be reopened; retrying inference: %s", exc)
        self._start_background_inference(settings)

    def _start_background_inference(self, settings: MaskPostprocessSettings) -> None:
        if self.original_player_source is None:
            return
        self._cancel_background_removal()
        request_id = self._background_request_id
        self._background_cancel = threading.Event()
        try:
            if self.background_removal_service is None:
                manager = BackgroundRemovalModelManager(background_removal_model_root(), self.logger)
                self.background_removal_service = BackgroundRemovalInferenceService(manager)
            worker = BackgroundRemovalWorker(
                request_id,
                self.background_removal_service,
                self.original_player_source.image,
                settings,
                self._background_cancel,
            )
            worker.signals.stage.connect(self._background_stage)
            worker.signals.completed.connect(
                lambda result_id, mask, elapsed: self._background_completed(
                    result_id, mask, elapsed, settings
                )
            )
            worker.signals.failed.connect(self._background_failed)
            worker.signals.cancelled.connect(self._background_cancelled)
            self._background_worker = worker
            self._background_progress = BackgroundRemovalProgressDialog(self.window)
            self._background_progress.canceled.connect(self._background_cancel.set)
            self._background_progress.show()
            QThreadPool.globalInstance().start(worker)
            self.logger.info("Started local background-removal request %s", request_id)
        except CardStudioError as exc:
            self._finish_background_progress()
            self._report_error("Background removal unavailable", exc)

    def _background_stage(self, request_id: int, stage: str) -> None:
        if request_id != self._background_request_id:
            return
        if self._background_progress is not None:
            self._background_progress.set_stage(stage)
        self._set_status(stage)

    def _background_completed(
        self,
        request_id: int,
        mask: Image.Image,
        elapsed: float,
        settings: MaskPostprocessSettings,
    ) -> None:
        if request_id != self._background_request_id or self._background_cancel.is_set():
            return
        self._finish_background_progress()
        self._last_inference_seconds = elapsed
        self.logger.info("Background-removal request %s completed in %.3fs", request_id, elapsed)
        self._show_background_result(mask, settings)

    def _background_failed(self, request_id: int, message: str) -> None:
        if request_id != self._background_request_id:
            return
        self._finish_background_progress()
        self.logger.error("Background-removal request %s failed: %s", request_id, message)
        show_error(
            self.window,
            "Background removal failed",
            message + "\n\nThe original image is unchanged and normal PNG importing remains available.",
            message,
        )

    def _background_cancelled(self, request_id: int) -> None:
        if request_id != self._background_request_id:
            return
        self._finish_background_progress()
        self._set_status("Background removal cancelled; original image preserved")

    def _finish_background_progress(self) -> None:
        if self._background_progress is not None:
            self._background_progress.close()
            self._background_progress.deleteLater()
            self._background_progress = None

    def _cancel_background_removal(self) -> None:
        self._background_cancel.set()
        self._background_request_id += 1
        self._finish_background_progress()

    def _show_background_result(
        self,
        automatic_mask: Image.Image,
        settings: MaskPostprocessSettings,
        current_mask: Image.Image | None = None,
    ) -> None:
        if self.original_player_source is None:
            return
        dialog = BackgroundRemovalDialog(
            self.original_player_source.image, automatic_mask, settings, self.window
        )
        if current_mask is not None:
            dialog.editor.mask = current_mask.copy()
        dialog.exec()
        if dialog.choice == "accept":
            self._accept_background_mask(
                dialog.accepted_mask(), automatic_mask, dialog.settings, dialog.was_manually_edited()
            )
        elif dialog.choice == "retry":
            self._start_background_inference(dialog.settings)
        elif dialog.choice == "restore":
            self.restore_original_background()

    def _accept_background_mask(
        self,
        mask: Image.Image,
        automatic_mask: Image.Image,
        settings: MaskPostprocessSettings,
        manually_edited: bool,
    ) -> None:
        if self.project is None or self.original_player_source is None:
            return
        original = self.original_player_source
        cutout = apply_alpha_mask(original.image, mask)
        self.player_source = LoadedPlayerImage(
            cutout, original.source_path, original.original_size, True, None
        )
        metadata = (
            self.background_removal_service.model_manager.metadata
            if self.background_removal_service is not None
            else None
        )
        state = self.project.background_removal
        state.enabled = True
        state.accepted_mask_png = encode_mask_png(mask)
        state.automatic_mask_png = encode_mask_png(automatic_mask)
        state.model_name = metadata.name if metadata else state.model_name
        state.model_version = metadata.version if metadata else state.model_version
        state.postprocessing = settings.to_dict()
        state.manually_edited = manually_edited
        self.project.modified = True
        self._sync_ui()
        self._push_history()
        self._set_status("Transparent cutout accepted; original RGB pixels preserved")

    def restore_original_background(self) -> None:
        if self.project is None or self.original_player_source is None:
            return
        self.player_source = self.original_player_source
        self.project.background_removal = self.project.background_removal.__class__()
        self.project.modified = True
        self._sync_ui()
        self._push_history()
        self._set_status("Original player image restored")

    def export_png(self) -> None:
        if self.project is None or self.template is None:
            return
        start = Path(str(self.settings.value("paths/export", self.paths.exports))) / "card.png"
        filename, _ = QFileDialog.getSaveFileName(self.window, "Export Native PNG", str(start), "PNG Images (*.png)")
        if not filename:
            return
        path = Path(filename).with_suffix(".png")
        if path.exists():
            answer = QMessageBox.question(self.window, "Overwrite PNG?", f"Replace existing file?\n{path}")
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            image = self.renderer.render_for_export(
                self.template,
                self.player_source.image if self.player_source else None,
                self.project.player_transform,
                self.project.text,
                logo_image=self.logo_image,
                logo=self.project.logo,
                background_image=self.background_image,
                promotion_image=self.promotion_image,
                promotion_asset_id=self.project.card_assets.promotion_logo_id,
            )
            ExportService.export_png(image, path, self.template.native_size)
            self.settings.set_value("paths/export", str(path.parent))
            self._set_status(f"Exported {image.width} x {image.height} RGBA PNG: {path}")
            self.logger.info("Exported PNG %s (%sx%s RGBA)", path, image.width, image.height)
        except CardStudioError as exc:
            self._report_error("Could not export PNG", exc)

    def _render_export_image(self):
        assert self.project is not None and self.template is not None
        return self.renderer.render_for_export(
            self.template,
            self.player_source.image if self.player_source else None,
            self.project.player_transform,
            self.project.text,
            logo_image=self.logo_image,
            logo=self.project.logo,
            background_image=self.background_image,
            promotion_image=self.promotion_image,
            promotion_asset_id=self.project.card_assets.promotion_logo_id,
        )

    def edit_player_data(self) -> None:
        if self.project is None:
            return
        data = self.project.player_data
        identity = data.setdefault("identity", {})
        card_name, card_year = self._player_identity_from_card_text(self.project.text.name)
        if card_name:
            identity["name"] = card_name
        if card_year is not None:
            identity["year"] = card_year
        if self.project.text.overall:
            try:
                identity["overall"] = int(self.project.text.overall)
            except ValueError:
                pass
        if self.project.text.position:
            identity["primary_position"] = self.project.text.position
        if self.template is not None:
            identity["tier"] = self.template.display_name
        if str(identity.get("franchise") or "").upper() == "UNASSIGNED":
            visible_logo = self.window.logo_combo.currentText().strip()
            if visible_logo and visible_logo != "No logo":
                identity["franchise"] = visible_logo
        self.project.player_data = apply_promotion_taxonomy(data, self.project.card_assets.promotion_logo_id)
        self.window.show_player_data_editor(self.project.player_data)

    def finish_player_data(self, data: dict) -> None:
        if self.project is None:
            self.window.show_card_editor()
            return
        self.project.player_data = apply_promotion_taxonomy(data, self.project.card_assets.promotion_logo_id)
        data = self.project.player_data
        identity = data.get("identity") or {}
        self.project.text.overall = normalize_overall(identity.get("overall"))
        self.project.text.position = normalize_position(identity.get("primary_position"))
        name = normalize_name(identity.get("name"))
        try:
            year = int(identity.get("year") or 2016)
            self.project.text.name = normalize_name(f"'{year % 100:02d} {name}") if name else ""
        except (TypeError, ValueError):
            self.project.text.name = name
        wanted_tier = str(identity.get("tier") or "").casefold()
        for index in range(self.window.template_combo.count()):
            if self.window.template_combo.itemText(index).casefold() == wanted_tier:
                self.window.template_combo.setCurrentIndex(index)
                break
        self.project.modified = True
        self.window.show_card_editor()
        self._sync_ui()
        self._push_history()
        self._set_status("Player attributes saved to this card project")

    def export_custom_card(self) -> None:
        if self.project is None or self.template is None:
            return
        identity = self.project.player_data.get("identity") or {}
        safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "", str(identity.get("name") or "custom-card")).strip() or "custom-card"
        start = Path(str(self.settings.value("paths/export", self.paths.exports))) / f"{safe_name}{CUSTOM_CARD_EXTENSION}"
        filename, _ = QFileDialog.getSaveFileName(
            self.window,
            "Export Card Image + NBA 2K16 Player Data",
            str(start),
            f"NBA 2K16 Custom Cards (*{CUSTOM_CARD_EXTENSION})",
        )
        if not filename:
            return
        path = Path(filename)
        if path.suffix.lower() != CUSTOM_CARD_EXTENSION:
            path = path.with_suffix(CUSTOM_CARD_EXTENSION)
        if path.exists():
            answer = QMessageBox.question(self.window, "Overwrite custom card?", f"Replace existing file?\n{path}")
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            image = self._render_export_image()
            CustomCardService.export(self.project, image, path, self.template.native_size)
            self.settings.set_value("paths/export", str(path.parent))
            self._set_status(f"Exported custom card image + complete player data: {path}")
            self.logger.info("Exported custom card package %s", path)
        except CardStudioError as exc:
            self._report_error("Could not export custom card", exc)

    def delete_player_image(self) -> None:
        if self.project is None or self.player_source is None:
            return
        self._cancel_background_removal()
        self.player_source = None
        self.original_player_source = None
        self.project.player_source_path = None
        self.project.background_removal = self.project.background_removal.__class__()
        self.project.modified = True
        self._sync_ui()
        self._push_history()

    def set_transform(self, x: float, y: float, scale: float, rotation: float, flipped: bool) -> None:
        if self.project is None:
            return
        self.project.player_transform = PlayerTransform(x, y, scale, rotation, flipped)
        self.project.modified = True
        self._sync_player_size_ui()
        self._sync_project_labels()
        self.render_preview()
        self._push_history()

    def set_text_fields(self, overall: str, position: str, player_name: str) -> None:
        if self.project is None:
            return
        normalized = (normalize_overall(overall), normalize_position(position), normalize_name(player_name))
        current = (self.project.text.overall, self.project.text.position, self.project.text.name)
        if normalized == current:
            return
        self.project.text.overall, self.project.text.position, self.project.text.name = normalized
        identity = self.project.player_data.setdefault("identity", {})
        identity_name, identity_year = self._player_identity_from_card_text(normalized[2])
        if identity_name:
            identity["name"] = identity_name
        if identity_year is not None:
            identity["year"] = identity_year
        self.project.modified = True
        self.window.player_controls.set_text_values(*normalized)
        self._sync_project_labels()
        self.render_preview()
        self._push_history()

    @staticmethod
    def _player_identity_from_card_text(value: object) -> tuple[str, int | None]:
        text = normalize_name(value)
        match = re.match(r"^\s*['’](\d{2})\s+(.+?)\s*$", text)
        if not match:
            return text, None
        short_year = int(match.group(1))
        year = 2000 + short_year if short_year <= 29 else 1900 + short_year
        return match.group(2).strip(), year

    def move_player(self, x: float, y: float) -> None:
        if self.project is None:
            return
        transform = self.project.player_transform
        transform.x, transform.y = round(x, 1), round(y, 1)
        self.project.modified = True
        self.window.player_controls.set_transform(transform)
        self._sync_project_labels()
        self.render_preview()
        self._push_history()

    def nudge_player(self, dx: int, dy: int) -> None:
        if self.project is None:
            return
        self.move_player(self.project.player_transform.x + dx, self.project.player_transform.y + dy)

    def scale_player(self, factor: float) -> None:
        if self.project is None or self.player_source is None or factor <= 0:
            return
        transform = self.project.player_transform
        new_scale = round(max(0.05, min(5.0, transform.scale * factor)), 6)
        if new_scale == transform.scale:
            return
        transform.scale = new_scale
        self.project.modified = True
        self.window.player_controls.set_transform(transform)
        self._sync_player_size_ui()
        self._sync_project_labels()
        self.render_preview()
        self._push_history()

    def set_player_scale_percent(self, value: float) -> None:
        """Apply a precise percentage entered in the top workflow bar."""
        if self.project is None:
            return
        transform = self.project.player_transform
        new_scale = round(max(0.05, min(5.0, value / 100.0)), 6)
        if new_scale == transform.scale:
            self._sync_player_size_ui()
            return
        transform.scale = new_scale
        self.project.modified = True
        self.window.player_controls.set_transform(transform)
        self._sync_player_size_ui()
        self._sync_project_labels()
        self.render_preview()
        self._push_history()

    def _populate_template_selector(self) -> None:
        choices: list[tuple[str, Path]] = []
        for directory in self.template_service.discover():
            try:
                template = self.template_service.load(directory)
                choices.append((template.display_name, directory))
            except TemplateValidationError:
                continue
        self.window.set_template_choices(choices)

    def _populate_logo_categories(self) -> None:
        self.window.set_logo_categories([(label, category_id) for category_id, label in LOGO_CATEGORIES])

    def _populate_card_assets(self) -> None:
        self.window.set_background_choices(
            [(asset.display_name, asset.asset_id) for asset in self.background_service.discover()]
        )
        self.window.set_promotion_choices(
            [(asset.display_name, asset.asset_id) for asset in self.promotion_service.discover()]
        )

    def _logo_category_changed(self, index: int) -> None:
        if index < 0 or self.project is None:
            return
        category = str(self.window.logo_category_combo.itemData(index) or "current")
        self.project.logo.category = category
        self.project.logo.asset_id = ""
        self.logo_image = None
        self.project.modified = True
        self._sync_logo_ui()
        self._sync_project_labels()
        self.render_preview()
        self._push_history()

    def _logo_selection_changed(self, index: int) -> None:
        if index < 0 or self.project is None:
            return
        asset_id = str(self.window.logo_combo.itemData(index) or "")
        if asset_id == self.project.logo.asset_id:
            return
        self.project.logo.asset_id = asset_id
        self.logo_image = self._load_project_logo(self.project)
        self.project.modified = True
        self._sync_project_labels()
        self.render_preview()
        self._push_history()

    def _background_selection_changed(self, index: int) -> None:
        if self.project is None:
            return
        asset_id = str(self.window.background_combo.itemData(index) or "") if index >= 0 else ""
        if asset_id == self.project.card_assets.background_id:
            return
        self.project.card_assets.background_id = asset_id
        self.background_image = self._load_project_card_asset(self.background_service, asset_id, "background")
        self.project.modified = True
        self._sync_project_labels()
        self.render_preview()
        self._push_history()

    def _promotion_selection_changed(self, index: int) -> None:
        if self.project is None:
            return
        asset_id = str(self.window.promotion_combo.itemData(index) or "") if index >= 0 else ""
        if asset_id == self.project.card_assets.promotion_logo_id:
            return
        self.project.card_assets.promotion_logo_id = asset_id
        self.project.player_data = apply_promotion_taxonomy(self.project.player_data, asset_id)
        self.promotion_image = self._load_project_card_asset(self.promotion_service, asset_id, "promotion logo")
        self.project.modified = True
        self._sync_project_labels()
        self.render_preview()
        self._push_history()

    def _template_selection_changed(self, index: int) -> None:
        if index < 0 or self.project is None:
            return
        value = self.window.template_combo.itemData(index)
        if not value:
            return
        directory = Path(str(value)).resolve()
        if self.template is not None and directory == self.template.directory.resolve():
            return
        # Tier selection is a frame swap. Keep the user's player placement
        # byte-for-byte equivalent instead of applying the next tier's import
        # defaults over an image they have already positioned.
        self._apply_template(directory, reset_transform=False)

    def open_readme(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.paths.readme)))

    def show_about(self) -> None:
        show_information(
            self.window,
            f"About {APPLICATION_NAME}",
            f"{APPLICATION_NAME} {APPLICATION_VERSION}\n\n"
            "Standalone deterministic card-template editor.\n"
            "This application is not part of the MyTEAM Companion App.",
        )

    def render_preview(self) -> None:
        if self.project is None or self.template is None:
            return
        result = self.renderer.render(
            self.template,
            self.player_source.image if self.player_source else None,
            self.project.player_transform,
            text=self.project.text,
            logo_image=self.logo_image,
            logo=self.project.logo,
            background_image=self.background_image,
            promotion_image=self.promotion_image,
            promotion_asset_id=self.project.card_assets.promotion_logo_id,
        )
        for layout in result.text_layouts:
            if layout.role in {"overall", "position", "name"}:
                self.project.text.fitted_scale[layout.role] = layout.scale
                self.project.text.fitted_tracking[layout.role] = layout.tracking
        self.window.player_controls.set_text_warning("\n".join(result.warnings))
        transform = self.project.player_transform
        self.window.canvas.set_render(result.image, result.player_hit_mask, transform.x, transform.y)

    def can_close(self) -> bool:
        if not self._maybe_continue():
            return False
        self._cancel_background_removal()
        self.settings.save_geometry(self.window.saveGeometry())
        self.settings.set_value("view/checkerboard", self.window.canvas.checkerboard_enabled())
        self.settings.set_value("view/zoom", self.window.canvas.zoom_setting())
        return True

    def _apply_template(self, directory: Path, reset_transform: bool = True) -> None:
        try:
            template = self.template_service.load(directory)
            self.template = template
            assert self.project is not None
            self.project.template = TemplateReference(template.template_id, str(template.directory))
            if reset_transform:
                defaults = template.player_defaults
                self.project.player_transform = PlayerTransform(
                    defaults.anchor_x, defaults.anchor_y, defaults.scale, defaults.rotation_degrees, defaults.flip_horizontal
                )
            self.project.modified = True
            self.settings.set_value("template/last", template.template_id)
            self.settings.set_value("template/last_path", str(template.directory))
            self._sync_ui()
            self._push_history()
            self.logger.info("Loaded template %s", template.directory)
        except CardStudioError as exc:
            self.logger.warning("Template validation failure: %s", exc)
            self._report_error("Template validation failed", exc)
            if self.template is not None:
                self.window.select_template_path(self.template.directory)

    def _load_project_template(self, project: CardProject) -> CardTemplate:
        attempts = [project.template.template_id]
        if project.template.path:
            path = Path(project.template.path)
            if not path.is_absolute() and project.file_path:
                path = (project.file_path.parent / path).resolve()
            attempts.append(path)
        errors = []
        for attempt in attempts:
            try:
                return self.template_service.load(attempt)
            except TemplateValidationError as exc:
                errors.extend(exc.errors)
        raise TemplateValidationError(errors or ["Project template could not be resolved."])

    def _sync_ui(self) -> None:
        if self.project is None or self.template is None:
            return
        self.window.player_controls.set_transform(self.project.player_transform)
        self._sync_player_size_ui()
        self.window.player_controls.set_text_values(
            self.project.text.overall, self.project.text.position, self.project.text.name
        )
        self._sync_logo_ui()
        if self.player_source:
            self.window.player_controls.set_source_info(*self.player_source.original_size, self.player_source.has_transparency)
        else:
            self.window.player_controls.clear_source_info()
        self.window.delete_image_action.setEnabled(self.player_source is not None)
        self.window.remove_background_action.setEnabled(self.original_player_source is not None)
        self.window.select_template_path(self.template.directory)
        self._sync_project_labels()
        self.render_preview()

    def _sync_player_size_ui(self) -> None:
        if self.project is not None:
            self.window.set_player_size_percent(self.project.player_transform.scale * 100.0)

    def _source_with_saved_mask(
        self, project: CardProject, original: LoadedPlayerImage
    ) -> LoadedPlayerImage:
        state = project.background_removal
        if not state.enabled or not state.accepted_mask_png:
            return original
        try:
            mask = decode_mask_png(state.accepted_mask_png, original.original_size)
            cutout = apply_alpha_mask(original.image, mask)
            return LoadedPlayerImage(
                cutout, original.source_path, original.original_size, True, None
            )
        except CardStudioError as exc:
            state.enabled = False
            self.logger.warning("Saved player mask was not applied: %s", exc)
            return original

    def _sync_project_labels(self) -> None:
        if self.project is None or self.template is None:
            return
        filename = self.project.file_path.name if self.project.file_path else "Untitled.2k16card"
        self.window.set_project_title(filename, self.project.modified)
        self.window.update_project_summary(filename, self.template.display_name, self.template.native_size, self.project.modified)
        self._set_status(
            f"Ready | Template: {self.template.display_name} | {self.template.canvas.width} x {self.template.canvas.height}"
        )

    def _snapshot(self) -> dict:
        assert self.project is not None
        return {
            "project": self.project.to_dict(),
            "file_path": str(self.project.file_path) if self.project.file_path else None,
            "modified": self.project.modified,
        }

    def _reset_history(self) -> None:
        self._history = [self._snapshot()] if self.project is not None else []
        self._history_index = 0 if self._history else -1
        self._update_history_actions()

    def _push_history(self) -> None:
        if self.project is None or self._restoring_history:
            return
        state = self._snapshot()
        if self._history_index >= 0 and self._history[self._history_index] == state:
            return
        del self._history[self._history_index + 1:]
        self._history.append(state)
        if len(self._history) > 100:
            self._history.pop(0)
        self._history_index = len(self._history) - 1
        self._update_history_actions()

    def _replace_current_history(self) -> None:
        if self.project is None:
            return
        if self._history_index < 0:
            self._reset_history()
        else:
            self._history[self._history_index] = self._snapshot()
            self._update_history_actions()

    def undo(self) -> None:
        if self._history_index <= 0:
            return
        self._history_index -= 1
        self._restore_history_state(self._history[self._history_index])

    def redo(self) -> None:
        if self._history_index < 0 or self._history_index >= len(self._history) - 1:
            return
        self._history_index += 1
        self._restore_history_state(self._history[self._history_index])

    def _restore_history_state(self, state: dict) -> None:
        self._restoring_history = True
        try:
            project = CardProject.from_dict(state["project"])
            project.file_path = Path(state["file_path"]) if state.get("file_path") else None
            project.modified = bool(state.get("modified", True))
            template = self._load_project_template(project)
            player_source = None
            original_player_source = None
            if project.player_source_path and Path(project.player_source_path).is_file():
                original_player_source = load_player_image(Path(project.player_source_path))
                player_source = self._source_with_saved_mask(project, original_player_source)
            self.project = project
            self.template = template
            self.player_source = player_source
            self.original_player_source = original_player_source
            self.logo_image = self._load_project_logo(project)
            self.background_image = self._load_project_card_asset(
                self.background_service, project.card_assets.background_id, "background"
            )
            self.promotion_image = self._load_project_card_asset(
                self.promotion_service, project.card_assets.promotion_logo_id, "promotion logo"
            )
            self._sync_ui()
        except CardStudioError as exc:
            self._report_error("Could not restore edit history", exc)
        finally:
            self._restoring_history = False
            self._update_history_actions()

    def _update_history_actions(self) -> None:
        self.window.undo_action.setEnabled(self._history_index > 0)
        self.window.redo_action.setEnabled(0 <= self._history_index < len(self._history) - 1)

    def _maybe_continue(self) -> bool:
        if self.project is None or not self.project.modified:
            return True
        answer = QMessageBox.question(
            self.window,
            "Unsaved changes",
            "Save changes before continuing?",
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Save,
        )
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Save:
            return self.save_project()
        return True

    def _restore_window(self) -> None:
        geometry = self.settings.restore_geometry()
        if geometry:
            self.window.restoreGeometry(geometry)
        self.window.canvas.set_checkerboard(True)
        self.window.canvas.set_zoom_fit()

    def _zoom_changed(self, display_value: str) -> None:
        self.settings.set_value("view/zoom", self.window.canvas.zoom_setting())
        self._set_status(f"Zoom: {display_value}")

    def _set_status(self, message: str) -> None:
        self.window.set_status(message)

    def _report_error(self, title: str, error: Exception) -> None:
        self.logger.exception("%s: %s", title, error)
        show_error(self.window, title, str(error), repr(error))

    @staticmethod
    def _image_filter() -> str:
        return "Player Images (*.png *.webp *.tif *.tiff *.jpg *.jpeg)"

    def _sync_logo_ui(self) -> None:
        if self.project is None:
            return
        logo = self.project.logo
        choices = [
            (asset.display_name, asset.asset_id)
            for asset in self.logo_service.discover(logo.category)
        ]
        self.window.set_logo_choices(choices, logo.asset_id)
        self.window.set_logo_state(logo.category, logo.asset_id)
        self.window.set_background_selection(self.project.card_assets.background_id)
        self.window.set_promotion_selection(self.project.card_assets.promotion_logo_id)

    def _load_project_logo(self, project: CardProject):
        if not project.logo.asset_id:
            return None
        try:
            return self.logo_service.load(project.logo.category, project.logo.asset_id)
        except CardStudioError as exc:
            self.logger.warning("Could not load project logo %s/%s: %s", project.logo.category, project.logo.asset_id, exc)
            project.logo.asset_id = ""
            return None

    def _load_project_card_asset(self, service: PngCardAssetService, asset_id: str, label: str):
        if not asset_id:
            return None
        try:
            return service.load(asset_id)
        except CardStudioError as exc:
            self.logger.warning("Could not load project %s %s: %s", label, asset_id, exc)
            if self.project is not None:
                if label == "background":
                    self.project.card_assets.background_id = ""
                else:
                    self.project.card_assets.promotion_logo_id = ""
            return None
