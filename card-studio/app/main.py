"""Standalone Card Studio application entry point."""

from __future__ import annotations

import sys

from PIL import Image, ImageDraw
from PySide6.QtCore import QCoreApplication, QTimer, Qt
from PySide6.QtGui import QFont, QGuiApplication, QIcon
from PySide6.QtWidgets import QApplication

from app.application import CardStudioApplication
from app.background_removal.model_manager import BackgroundRemovalModelManager
from app.background_removal.inference_service import BackgroundRemovalInferenceService
from app.constants import APPLICATION_ID, APPLICATION_NAME, APPLICATION_VERSION, BUILT_IN_TEMPLATE_ORDER, ORGANIZATION_NAME
from app.utilities.logging_setup import configure_logging
from app.utilities.paths import AppPaths, background_removal_model_root


def create_qt_application(arguments: list[str] | None = None) -> QApplication:
    QCoreApplication.setOrganizationName(ORGANIZATION_NAME)
    QCoreApplication.setApplicationName(APPLICATION_ID)
    QCoreApplication.setApplicationVersion(APPLICATION_VERSION)
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    application = QApplication(arguments if arguments is not None else sys.argv)
    application.setApplicationDisplayName(APPLICATION_NAME)
    application.setStyle("Fusion")
    application.setFont(QFont("Segoe UI", 10))
    return application


def main() -> int:
    paths = AppPaths.create()
    logger = configure_logging(paths.logs)
    model_manager = BackgroundRemovalModelManager(background_removal_model_root(), logger)
    model_manager.validate_model()
    qt_app = create_qt_application()
    icon_path = paths.root / "assets" / "application" / "card-studio.ico"
    if icon_path.is_file():
        qt_app.setWindowIcon(QIcon(str(icon_path)))
    controller = CardStudioApplication(qt_app, paths, logger)
    controller.show()
    if "--smoke-test" in sys.argv:
        # Exercise bundled templates, atlases, normalization, and the complete
        # preview renderer before returning success to packaging automation.
        discovered = controller.template_service.discover()
        if tuple(path.name for path in discovered) != BUILT_IN_TEMPLATE_ORDER:
            raise RuntimeError(f"Packaged tier discovery failed: {[path.name for path in discovered]}")
        expected_logo_counts = {"current": 31, "historic": 46, "euroleague": 25}
        for category, expected_count in expected_logo_counts.items():
            assets = controller.logo_service.discover(category)
            if len(assets) != expected_count:
                raise RuntimeError(f"Packaged {category} logo discovery failed: {len(assets)}")
        backgrounds = controller.background_service.discover()
        promotions = controller.promotion_service.discover()
        if len(backgrounds) != 11:
            raise RuntimeError(f"Packaged background discovery failed: {len(backgrounds)}")
        if len(promotions) != 13:
            raise RuntimeError(f"Packaged promotion-logo discovery failed: {len(promotions)}")
        usa_logo = next((item for item in promotions if item.asset_id == "usa_olympic"), None)
        if usa_logo is None:
            raise RuntimeError("Packaged promotion-logo discovery missing USA Olympic")
        smoke_source = Image.new("RGB", (64, 96), (30, 30, 30))
        ImageDraw.Draw(smoke_source).ellipse((14, 10, 50, 82), fill=(230, 230, 230))
        smoke_mask, _elapsed = BackgroundRemovalInferenceService(model_manager).generate_mask(smoke_source)
        if smoke_mask.size != (64, 96):
            raise RuntimeError("Packaged background-removal inference returned the wrong mask size")
        current_logo = controller.logo_service.discover("current")[0]
        assert controller.project is not None
        controller.project.logo.category = "current"
        controller.project.logo.asset_id = current_logo.asset_id
        controller.logo_image = controller.logo_service.load("current", current_logo.asset_id)
        controller.project.card_assets.background_id = backgrounds[0].asset_id
        controller.project.card_assets.promotion_logo_id = usa_logo.asset_id
        controller.background_image = controller.background_service.load(backgrounds[0].asset_id)
        controller.promotion_image = controller.promotion_service.load(usa_logo.asset_id)
        if controller.promotion_image is None:
            raise RuntimeError("Packaged USA Olympic promotion logo failed to load")
        for directory in discovered:
            controller._apply_template(directory)
            controller.set_text_fields("97", "PG", "KENTAVIOUS CALDWELL-POPE")
            assert controller.project is not None
            assert controller.template is not None
            result = controller.renderer.render(
                controller.template,
                None,
                controller.project.player_transform,
                text=controller.project.text,
                logo_image=controller.logo_image,
                logo=controller.project.logo,
                background_image=controller.background_image,
                promotion_image=controller.promotion_image,
                promotion_asset_id=controller.project.card_assets.promotion_logo_id,
            )
            if result.warnings or len(result.text_layouts) != 4:
                raise RuntimeError(f"Packaged {directory.name} text-render smoke test failed: {result.warnings}")
        controller.project.modified = False
        QTimer.singleShot(250, qt_app.quit)
    return qt_app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
