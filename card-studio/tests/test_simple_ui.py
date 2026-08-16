from __future__ import annotations

import logging
import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QPoint, QPointF, Qt
from PySide6.QtGui import QKeyEvent, QWheelEvent
from PySide6.QtWidgets import QApplication, QDoubleSpinBox, QLineEdit, QTabWidget

from app.application import CardStudioApplication
from app.rendering.image_loader import load_player_image
from app.ui.canvas_widget import CardCanvasWidget
from app.ui.main_window import MainWindow
from app.ui.player_data_editor import PlayerDataEditor
from app.player_data.preset_database import PlayerPresetDatabase
from app.utilities.paths import AppPaths


STUDIO_ROOT = Path(__file__).resolve().parents[1]


def make_paths(tmp_path: Path) -> AppPaths:
    paths = AppPaths(
        root=STUDIO_ROOT,
        templates=STUDIO_ROOT / "assets" / "built_in_templates",
        readme=STUDIO_ROOT / "README.md",
        user_data=tmp_path,
        projects=tmp_path / "projects",
        exports=tmp_path / "exports",
        logs=tmp_path / "logs",
        builder_projects=tmp_path / "builder-projects",
        builder_autosaves=tmp_path / "builder-autosaves",
        builder_backups=tmp_path / "builder-backups",
    )
    paths.ensure_writable_directories()
    return paths


@pytest.fixture(scope="module")
def qt_app():
    application = QApplication.instance() or QApplication(["card-studio-tests"])
    yield application


def test_main_window_exposes_one_simple_card_workspace(qt_app):
    window = MainWindow()

    assert not isinstance(window.centralWidget(), QTabWidget)
    assert [action.text() for action in window.menuBar().actions()] == ["File", "Edit", "Help"]
    assert set(window.workflow_buttons) == {
        "importButton",
        "removeBackgroundButton",
        "deleteButton",
        "openButton",
        "saveButton",
        "primaryButton",
        "exportCustomButton",
        "undoButton",
        "redoButton",
    }
    assert not hasattr(window, "builder_workspace")
    assert not hasattr(window, "layer_panel")
    assert window.player_controls.findChildren(QDoubleSpinBox) == [
        window.player_controls.x,
        window.player_controls.y,
    ]
    text_inputs = [item for item in window.player_controls.findChildren(QLineEdit) if not item.objectName().startswith("qt_")]
    assert text_inputs == [
        window.player_controls.overall,
        window.player_controls.position,
        window.player_controls.player_name,
    ]
    assert not hasattr(window, "logo_size")
    assert window.player_size.suffix() == " %"
    assert window.player_size.decimals() == 2
    assert window.player_size.singleStep() == pytest.approx(0.25)
    assert window.background_combo.itemText(0) == "No background"
    assert window.promotion_combo.itemText(0) == "No promotion logo"


def test_player_data_editor_omits_gear_tab_and_humanizes_dunk_names(qt_app):
    editor = PlayerDataEditor()
    tab_names = [editor.tabs.tabText(index) for index in range(editor.tabs.count())]
    assert tab_names == [
        "Vitals", "Attributes", "Tendencies", "Signature Animations", "Badges", "Hot Zones",
    ]
    assert PlayerDataEditor._dunk_choice_label("TwoFootTwoHandFISTPUMPRIMPULLS") == (
        "Two Foot Two Hand Fist Pump Rim Pulls"
    )
    assert PlayerDataEditor._dunk_choice_label("TwoFootOneHandLEANINGWINDMILLS") == (
        "Two Foot One Hand Leaning Windmills"
    )
    assert "identity.wingspan_inches" not in editor._controls
    assert "identity.wingspan_value" not in editor._controls
    jersey = editor._controls["identity.jersey_number"]
    double_zero = jersey.findText("00")
    assert double_zero >= 0
    assert jersey.itemData(double_zero) == "00"
    editor.set_player_data({"identity": {"jersey_number": "00"}})
    assert jersey.currentText() == "00"


def test_player_preset_search_applies_known_data_and_keeps_controls_editable(qt_app):
    editor = PlayerDataEditor()
    database = PlayerPresetDatabase(
        presets=({
            "label": "Ray Allen — 2008 — 87 OVR — Boston Celtics",
            "name": "Ray Allen",
            "patch": {
                "identity": {
                    "name": "Ray Allen", "year": 2008, "theme": "Historic",
                    "collection": "Celtics Franchise", "jersey_number": 20,
                    "face_id": 123, "portrait_id": 456,
                    "source_card_id": 777, "source_card_slug": "ray-allen",
                },
                "tendencies": {"shot_three": 91},
                "signatures": {"shooting_form": 127},
                "hot_zones": {"three_center": 2},
            },
        },),
        themes=("Current", "Historic"),
        collections=("Current Players", "Celtics Franchise"),
        theme_collections={"Current": ("Current Players",), "Historic": ("Celtics Franchise",)},
    )
    editor.set_preset_database(database)
    editor.set_player_data({"identity": {"name": "Custom Shooter", "year": 2021}})
    player = editor._preset_combo
    assert player is not None
    assert player.isEditable() and player.completer() is not None
    editor._apply_selected_preset(0)
    data = editor.player_data()
    assert data["identity"]["name"] == "Custom Shooter"
    assert data["identity"]["year"] == 2021
    assert data["identity"]["jersey_number"] == 20
    assert data["identity"]["face_id"] == 123
    assert data["identity"]["portrait_id"] == 456
    assert data["identity"]["source_card_id"] == 777
    assert data["identity"]["source_card_slug"] == "ray-allen"
    assert data["tendencies"]["shot_three"] == 91
    assert data["signatures"]["shooting_form"] == 127
    assert data["hot_zones"]["three_center"] == 2
    editor._controls["tendencies.shot_three"].setValue(95)
    assert editor.player_data()["tendencies"]["shot_three"] == 95


def test_card_text_inputs_normalize_and_update_preview(qt_app, tmp_path):
    controller = CardStudioApplication(qt_app, make_paths(tmp_path), logging.getLogger("card-text-ui-test"))
    controller.set_text_fields("097", "pg", "  c.j.   mccollum ")
    assert controller.project is not None
    assert controller.project.text.overall == "97"
    assert controller.project.text.position == "PG"
    assert controller.project.text.name == "C.J. MCCOLLUM"
    assert controller.window.player_controls.overall.text() == "97"
    assert controller.window.player_controls.position.text() == "PG"
    assert controller.window.player_controls.player_name.text() == "C.J. MCCOLLUM"
    assert not controller.window.player_controls.text_warning.isVisible()


def test_card_name_prefix_updates_custom_identity_name_and_year(qt_app, tmp_path):
    controller = CardStudioApplication(qt_app, make_paths(tmp_path), logging.getLogger("card-year-test"))
    controller.set_text_fields("90", "PF", "'21 Giannis Antetokounmpo")
    assert controller.project.player_data["identity"]["name"] == "GIANNIS ANTETOKOUNMPO"
    assert controller.project.player_data["identity"]["year"] == 2021
    controller.set_text_fields("90", "PG", "'89 Kenny Smith")
    assert controller.project.player_data["identity"]["name"] == "KENNY SMITH"
    assert controller.project.player_data["identity"]["year"] == 1989


def test_logo_menus_default_to_current_and_switch_categories(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("NBA2K16_CARD_STUDIO_DATA_DIR", str(tmp_path / "data"))
    controller = CardStudioApplication(qt_app, make_paths(tmp_path), logging.getLogger("logo-ui-test"))
    assert controller.project is not None
    assert [
        controller.window.logo_category_combo.itemText(index)
        for index in range(controller.window.logo_category_combo.count())
    ] == ["Current", "Historic", "EuroLeague"]
    assert controller.window.logo_category_combo.currentData() == "current"
    assert controller.window.logo_combo.count() == 32  # No logo + 31 current choices

    controller.window.logo_category_combo.setCurrentIndex(
        controller.window.logo_category_combo.findData("historic")
    )
    assert controller.project.logo.category == "historic"
    assert controller.window.logo_combo.count() == 47
    controller.window.logo_category_combo.setCurrentIndex(
        controller.window.logo_category_combo.findData("euroleague")
    )
    assert controller.project.logo.category == "euroleague"
    assert controller.window.logo_combo.count() == 26


def test_logo_background_and_promotion_selections_are_undoable(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("NBA2K16_CARD_STUDIO_DATA_DIR", str(tmp_path / "data"))
    controller = CardStudioApplication(qt_app, make_paths(tmp_path), logging.getLogger("logo-history-test"))
    assert controller.project is not None
    logo_index = controller.window.logo_combo.findData("Atlanta Hawks.png")
    controller.window.logo_combo.setCurrentIndex(logo_index)
    assert controller.project.logo.asset_id == "Atlanta Hawks.png"
    assert controller.logo_image is not None
    background_index = controller.window.background_combo.findData("theme_current")
    controller.window.background_combo.setCurrentIndex(background_index)
    assert controller.project.card_assets.background_id == "theme_current"
    promotion_index = controller.window.promotion_combo.findData("current_player")
    controller.window.promotion_combo.setCurrentIndex(promotion_index)
    assert controller.project.card_assets.promotion_logo_id == "current_player"
    controller.undo()
    assert controller.project.card_assets.promotion_logo_id == ""
    assert controller.project.card_assets.background_id == "theme_current"
    assert controller.project.logo.asset_id == "Atlanta Hawks.png"
    controller.redo()
    assert controller.project.card_assets.promotion_logo_id == "current_player"


def test_card_editor_undo_and_redo_restore_player_position(qt_app, tmp_path):
    controller = CardStudioApplication(qt_app, make_paths(tmp_path), logging.getLogger("simple-ui-test"))
    assert controller.project is not None
    assert [controller.window.template_combo.itemText(index) for index in range(controller.window.template_combo.count())] == [
        "Pink Diamond", "Diamond", "Amethyst", "Gold", "Silver", "Bronze"
    ]
    start_x = controller.project.player_transform.x
    start_y = controller.project.player_transform.y

    controller.move_player(start_x + 12, start_y - 7)
    assert controller.window.undo_action.isEnabled()
    controller.undo()
    assert controller.project.player_transform.x == start_x
    assert controller.project.player_transform.y == start_y
    assert controller.window.redo_action.isEnabled()
    controller.redo()
    assert controller.project.player_transform.x == start_x + 12
    assert controller.project.player_transform.y == start_y - 7


def test_tier_menu_preserves_exact_player_transform(qt_app, tmp_path, monkeypatch):
    monkeypatch.setenv("NBA2K16_CARD_STUDIO_DATA_DIR", str(tmp_path / "data"))
    controller = CardStudioApplication(qt_app, make_paths(tmp_path), logging.getLogger("tier-transform-test"))
    assert controller.project is not None
    player_path = tmp_path / "placed-player.png"
    Image.new("RGBA", (73, 141), (240, 80, 20, 220)).save(player_path)
    controller.player_source = load_player_image(player_path)
    controller.project.player_source_path = str(player_path)
    controller.project.player_transform.x = 143.7
    controller.project.player_transform.y = 391.4
    controller.project.player_transform.scale = 0.7312
    controller.project.player_transform.rotation_degrees = 13.5
    controller.project.player_transform.flip_horizontal = True
    expected = controller.project.player_transform.to_dict()

    for index in range(controller.window.template_combo.count()):
        controller.window.template_combo.setCurrentIndex(index)
        assert controller.project.player_transform.to_dict() == expected


def test_ctrl_wheel_requests_player_scaling(qt_app):
    canvas = CardCanvasWidget()
    factors: list[float] = []
    canvas.player_scale_requested.connect(factors.append)
    event = QWheelEvent(
        QPointF(20, 20),
        QPointF(20, 20),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )

    canvas.wheelEvent(event)

    assert factors == pytest.approx([1.01])
    assert event.isAccepted()


def test_delete_key_on_canvas_requests_player_deletion(qt_app):
    canvas = CardCanvasWidget()
    requests: list[bool] = []
    canvas.player_delete_requested.connect(lambda: requests.append(True))
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Delete, Qt.KeyboardModifier.NoModifier)

    canvas.keyPressEvent(event)

    assert requests == [True]
    assert event.isAccepted()


def test_ctrl_wheel_scale_is_undoable(qt_app, tmp_path):
    controller = CardStudioApplication(qt_app, make_paths(tmp_path), logging.getLogger("scale-history-test"))
    assert controller.project is not None
    player_path = tmp_path / "player.png"
    Image.new("RGBA", (24, 40), (255, 255, 255, 0)).save(player_path)
    controller.player_source = load_player_image(player_path)
    controller.project.player_source_path = str(player_path)
    controller.project.modified = True
    controller._push_history()
    original_scale = controller.project.player_transform.scale

    controller.scale_player(1.01)
    assert controller.project.player_transform.scale == pytest.approx(original_scale * 1.01)
    assert controller.window.player_size.value() == pytest.approx(original_scale * 101.0)
    controller.undo()
    assert controller.project.player_transform.scale == original_scale
    controller.redo()
    assert controller.project.player_transform.scale == pytest.approx(original_scale * 1.01)


def test_precise_player_size_percent_is_undoable(qt_app, tmp_path):
    controller = CardStudioApplication(qt_app, make_paths(tmp_path), logging.getLogger("precise-scale-test"))
    assert controller.project is not None
    original_scale = controller.project.player_transform.scale

    controller.window.player_size.setValue(37.25)

    assert controller.project.player_transform.scale == pytest.approx(0.3725)
    assert controller.window.player_size.value() == pytest.approx(37.25)
    controller.undo()
    assert controller.project.player_transform.scale == pytest.approx(original_scale)
    assert controller.window.player_size.value() == pytest.approx(original_scale * 100.0)
    controller.redo()
    assert controller.project.player_transform.scale == pytest.approx(0.3725)
    assert controller.window.player_size.value() == pytest.approx(37.25)


def test_delete_png_is_undoable(qt_app, tmp_path):
    controller = CardStudioApplication(qt_app, make_paths(tmp_path), logging.getLogger("delete-history-test"))
    assert controller.project is not None
    player_path = tmp_path / "deletable-player.png"
    Image.new("RGBA", (24, 40), (255, 255, 255, 0)).save(player_path)
    controller.player_source = load_player_image(player_path)
    controller.project.player_source_path = str(player_path)
    controller.project.modified = True
    controller._sync_ui()
    controller._push_history()
    assert controller.window.delete_image_action.isEnabled()

    controller.delete_player_image()
    assert controller.player_source is None
    assert controller.project.player_source_path is None
    assert not controller.window.delete_image_action.isEnabled()
    controller.undo()
    assert controller.player_source is not None
    assert controller.project.player_source_path == str(player_path)
    assert controller.window.delete_image_action.isEnabled()
    controller.redo()
    assert controller.player_source is None
    assert controller.project.player_source_path is None
