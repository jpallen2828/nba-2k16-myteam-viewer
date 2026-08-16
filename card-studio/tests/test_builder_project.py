import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from app.builder.models import BuilderProject, PatchOperation, SourceCard, SourceTransform
from app.builder.services.autosave_service import AutosaveService
from app.builder.services.project_service import BuilderProjectError, BuilderProjectService
from app.builder.services.source_service import SourceImportError, SourceService


def source_file(path: Path, color=(10, 20, 30, 255), size=(12, 16)) -> Path:
    Image.new("RGBA", size, color).save(path)
    return path


def test_new_builder_project_has_named_masks_and_border_alignment():
    project = BuilderProject.create("Synthetic", "synthetic", 12, 16)
    assert project.width == 12
    assert {"alignment", "foreground", "background", "player_art", "unresolved"} <= set(project.masks)
    alignment = project.masks["alignment"].array()
    assert alignment[0, 0] == 255
    assert alignment[8, 6] == 0


def test_text_layout_metadata_persists_for_future_fitting(tmp_path):
    project = BuilderProject.create("Synthetic", "synthetic", 12, 16)
    region = project.text_regions["name"]
    region.safe_inset_left = 3
    region.safe_inset_right = 4
    region.safe_inset_top = 1
    region.safe_inset_bottom = 2
    region.force_uppercase = True
    region.fit_mode = "tighten_tracking_then_scale"
    region.min_scale = .62
    region.preferred_tracking = -.25
    path = BuilderProjectService().save(project, tmp_path / "layout.2k16templatework")
    restored = BuilderProjectService().load(path).text_regions["name"]
    assert (restored.safe_inset_left, restored.safe_inset_right, restored.safe_inset_top, restored.safe_inset_bottom) == (3, 4, 1, 2)
    assert restored.force_uppercase and restored.fit_mode == "tighten_tracking_then_scale"
    assert restored.min_scale == .62 and restored.preferred_tracking == -.25


def test_builder_save_reload_persists_transform_masks_text_and_patches(tmp_path):
    project = BuilderProject.create("Synthetic", "synthetic", 12, 16)
    path = source_file(tmp_path / "source.png")
    loaded = SourceService().import_source(path, project)
    project.sources.append(loaded.model)
    project.set_reference(loaded.model.source_id)
    loaded.model.transform = SourceTransform((1, 2, 10, 14), None, 3, -2, 1.01, 0.5, True)
    project.masks["foreground"].rectangle((1, 2, 5, 7), 255)
    project.text_regions["name"].x = 2
    project.text_regions["name"].width = 8
    project.patches.append(PatchOperation(loaded.model.source_id, [(2, 3)], 1, 0))
    project.manual_pixels["4,5"] = [1, 2, 3, 4]
    destination = BuilderProjectService(tmp_path / "backups").save(project, tmp_path / "work")
    restored = BuilderProjectService().load(destination)
    assert destination.suffix == ".2k16templatework"
    assert restored.sources[0].transform.crop_rect == (1.0, 2.0, 10.0, 14.0)
    assert restored.sources[0].transform.subpixel is True
    assert restored.masks["foreground"].array()[3, 2] == 255
    assert restored.text_regions["name"].width == 8
    assert restored.patches[0].points == [(2, 3)]
    assert restored.manual_pixels["4,5"] == [1, 2, 3, 4]


def test_builder_project_uses_relative_source_path_when_practical(tmp_path):
    project = BuilderProject.create("Synthetic", "synthetic", 12, 16)
    source = source_file(tmp_path / "source.png")
    project.sources.append(SourceService().import_source(source, project).model)
    path = BuilderProjectService().save(project, tmp_path / "project.2k16templatework")
    raw = json.loads(path.read_text())
    assert raw["sources"][0]["path"] == "source.png"
    assert Path(BuilderProjectService().load(path).sources[0].path) == source.resolve()


def test_builder_version_and_application_validation(tmp_path):
    project = BuilderProject.create("Synthetic", "synthetic", 4, 4)
    payload = project.to_dict()
    payload["project_version"] = 99
    path = tmp_path / "bad.2k16templatework"
    path.write_text(json.dumps(payload))
    with pytest.raises(BuilderProjectError, match="Unsupported Builder project version"):
        BuilderProjectService().load(path)


def test_autosave_recovery_round_trip(tmp_path):
    project = BuilderProject.create("Recover", "recover", 9, 11)
    project.manual_pixels["1,2"] = [9, 8, 7, 6]
    service = AutosaveService(tmp_path)
    service.write(project)
    assert service.available()
    restored = service.load()
    assert restored.manual_pixels["1,2"] == [9, 8, 7, 6]
    assert restored.modified
    service.clear()
    assert not service.available()


def test_source_import_warnings_and_duplicate_detection(tmp_path):
    project = BuilderProject.create("Synthetic", "synthetic", 12, 16)
    path = source_file(tmp_path / "source.png")
    service = SourceService()
    first = service.import_source(path, project); project.sources.append(first.model)
    second = service.import_source(path, project)
    assert any("exact file" in item for item in second.model.warnings)
    assert any("Pixel content" in item for item in second.model.warnings)


def test_dimension_mismatch_is_disabled_not_silently_resized(tmp_path):
    project = BuilderProject.create("Synthetic", "synthetic", 12, 16)
    loaded = SourceService().import_source(source_file(tmp_path / "wide.png", size=(20, 16)), project)
    assert not loaded.model.enabled
    assert "normalize before analysis" in " ".join(loaded.model.warnings)


def test_relink_rejects_different_pixels(tmp_path):
    project = BuilderProject.create("Synthetic", "synthetic", 12, 16)
    service = SourceService()
    loaded = service.import_source(source_file(tmp_path / "one.png"), project)
    with pytest.raises(SourceImportError, match="does not match"):
        service.relink(loaded.model, source_file(tmp_path / "other.png", (90, 80, 70, 255)))
