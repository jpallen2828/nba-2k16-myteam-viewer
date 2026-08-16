from __future__ import annotations

import json
import hashlib
import logging
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from app.background_removal.cutout_service import apply_alpha_mask, decode_mask_png, encode_mask_png
from app.background_removal.exceptions import InferenceCancelled, ModelMissingError, ModelValidationError
from app.background_removal.inference_service import BackgroundRemovalInferenceService
from app.background_removal.mask_postprocessing import MaskPostprocessSettings, postprocess_mask
from app.background_removal.model_manager import BackgroundRemovalModelManager
from app.background_removal.model_metadata import ModelMetadata
from app.application import CardStudioApplication
from app.rendering.image_loader import load_player_image
from app.utilities.paths import AppPaths, background_removal_model_root
from app.ui.mask_editor_widget import MaskEditorWidget


@pytest.fixture(scope="module")
def qt_app():
    return QApplication.instance() or QApplication(["background-removal-tests"])


def test_cutout_preserves_original_rgb_and_dimensions():
    pixels = np.array(
        [[[10, 20, 30, 255], [40, 50, 60, 255]], [[70, 80, 90, 255], [100, 110, 120, 255]]],
        dtype=np.uint8,
    )
    original = Image.fromarray(pixels, mode="RGBA")
    mask = Image.fromarray(np.array([[0, 64], [128, 255]], dtype=np.uint8), mode="L")
    result = apply_alpha_mask(original, mask)
    result_values = np.asarray(result)
    assert result.mode == "RGBA"
    assert result.size == original.size
    assert np.array_equal(result_values[:, :, :3], pixels[:, :, :3])
    assert np.array_equal(result_values[:, :, 3], np.asarray(mask))
    assert int(result_values[:, :, 3].min()) == 0


def test_mask_png_round_trip_is_deterministic():
    mask = Image.fromarray(np.arange(100, dtype=np.uint8).reshape(10, 10), mode="L")
    encoded = encode_mask_png(mask)
    decoded = decode_mask_png(encoded, mask.size)
    assert np.array_equal(np.asarray(decoded), np.asarray(mask))
    assert encode_mask_png(decoded) == encoded


def test_existing_transparent_png_is_preserved(tmp_path):
    path = tmp_path / "transparent.png"
    source = Image.new("RGBA", (7, 9), (12, 34, 56, 255))
    source.putpixel((3, 4), (99, 88, 77, 0))
    source.save(path)
    loaded = load_player_image(path)
    assert loaded.has_transparency
    assert np.array_equal(np.asarray(loaded.image), np.asarray(source))


def test_postprocessing_default_is_identity_and_threshold_is_conservative():
    mask = Image.fromarray(np.array([[0, 4, 128, 255]], dtype=np.uint8), mode="L")
    assert np.array_equal(np.asarray(postprocess_mask(mask, MaskPostprocessSettings())), np.asarray(mask))
    thresholded = postprocess_mask(mask, MaskPostprocessSettings(threshold=5))
    assert np.array_equal(np.asarray(thresholded), np.array([[0, 0, 128, 255]], dtype=np.uint8))


def test_mask_editor_restore_remove_undo_redo_and_reset(qt_app):
    original = Image.new("RGBA", (40, 40), (120, 80, 40, 255))
    automatic = Image.new("L", (40, 40), 128)
    editor = MaskEditorWidget(original, automatic)
    before = np.asarray(editor.current_mask()).copy()
    editor._undo.append(editor.current_mask())
    editor.set_brush("restore", 12, 1.0, False)
    editor._dab(20, 20)
    restored = np.asarray(editor.current_mask()).copy()
    assert restored[20, 20] == 255
    editor.undo()
    assert np.array_equal(np.asarray(editor.current_mask()), before)
    editor.redo()
    assert np.array_equal(np.asarray(editor.current_mask()), restored)
    editor._undo.append(editor.current_mask())
    editor.set_brush("remove", 12, 1.0, False)
    editor._dab(20, 20)
    assert np.asarray(editor.current_mask())[20, 20] == 0
    editor.reset_automatic()
    assert np.array_equal(np.asarray(editor.current_mask()), before)


class _FakeInput:
    name = "input"


class _FakeSession:
    def get_inputs(self):
        return [_FakeInput()]

    def run(self, _outputs, feed):
        assert feed["input"].shape == (1, 3, 8, 8)
        logits = np.linspace(-8, 8, 64, dtype=np.float32).reshape(1, 1, 8, 8)
        return [logits]


class _FakeManager:
    metadata = ModelMetadata(
        "fake", "1", "fake.onnx", (8, 8), (0.485, 0.456, 0.406),
        (0.229, 0.224, 0.225), "logits", "MIT", "local", "0" * 64
    )

    def session(self):
        return _FakeSession()


def test_inference_is_repeatable_and_cancellable():
    service = BackgroundRemovalInferenceService(_FakeManager())
    source = Image.new("RGB", (13, 17), (30, 60, 90))
    first, _ = service.generate_mask(source)
    second, _ = service.generate_mask(source)
    assert first.size == source.size
    assert np.array_equal(np.asarray(first), np.asarray(second))
    with pytest.raises(InferenceCancelled):
        service.generate_mask(source, cancelled=lambda: True)


def _write_metadata(directory: Path, sha256: str = "0" * 64) -> None:
    data = {
        "model_name": "test", "version": "1", "filename": "model.onnx",
        "expected_input_size": [8, 8],
        "normalization": {"mean": [0, 0, 0], "std": [1, 1, 1]},
        "output_interpretation": "test", "license": "MIT", "source_url": "local", "sha256": sha256,
    }
    (directory / "model.json").write_text(json.dumps(data), encoding="utf-8")


def test_missing_and_corrupt_models_fail_cleanly(tmp_path):
    _write_metadata(tmp_path)
    manager = BackgroundRemovalModelManager(tmp_path)
    with pytest.raises(ModelMissingError):
        manager.validate_model()
    (tmp_path / "model.onnx").write_bytes(b"not an onnx model")
    with pytest.raises(ModelValidationError, match="integrity"):
        manager.validate_model()

    payload = b"not an onnx model but checksum-valid"
    (tmp_path / "model.onnx").write_bytes(payload)
    _write_metadata(tmp_path, hashlib.sha256(payload).hexdigest())
    corrupt = BackgroundRemovalModelManager(tmp_path)
    with pytest.raises(ModelValidationError, match="Could not load"):
        corrupt.session()


def test_packaged_model_path_is_next_to_executable(monkeypatch, tmp_path):
    executable = tmp_path / "portable" / "NBA2K16CardStudio.exe"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    assert background_removal_model_root() == executable.parent / "models"


def test_packaged_model_path_falls_back_to_embedded_bundle(monkeypatch, tmp_path):
    executable = tmp_path / "portable" / "NBA2K16CardStudio.exe"
    bundle = tmp_path / "bundle"
    (bundle / "models").mkdir(parents=True)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(executable))
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle), raising=False)
    assert background_removal_model_root() == bundle / "models"


def _paths(tmp_path: Path) -> AppPaths:
    root = Path(__file__).resolve().parents[1]
    paths = AppPaths(
        root=root,
        templates=root / "assets" / "built_in_templates",
        readme=root / "README.md",
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


def test_stale_or_cancelled_result_cannot_open_preview(qt_app, tmp_path, monkeypatch):
    controller = CardStudioApplication(qt_app, _paths(tmp_path), logging.getLogger("stale-mask-test"))
    shown: list[bool] = []
    monkeypatch.setattr(controller, "_show_background_result", lambda *_args: shown.append(True))
    controller._background_request_id = 4
    mask = Image.new("L", (8, 8), 255)
    controller._background_completed(3, mask, 0.1, MaskPostprocessSettings())
    assert shown == []
    controller._background_cancel.set()
    controller._background_completed(4, mask, 0.1, MaskPostprocessSettings())
    assert shown == []
