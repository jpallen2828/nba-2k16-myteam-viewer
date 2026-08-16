import json
from pathlib import Path

import numpy as np
from PIL import Image
import pytest

from app.builder.analysis.composite import generate_composite
from app.builder.models import BuilderProject, SourceCard
from app.builder.rendering import BuilderRenderState
from app.builder.services.template_export_service import TemplateExportError, TemplateExportService
from app.services.template_service import TemplateService


def export_state(project):
    image = Image.new("RGBA", (project.width, project.height), (30, 50, 70, 255))
    result = generate_composite([image, image])
    project.masks["background"].fill(255)
    project.masks["foreground"].rectangle((0, 0, project.width - 1, 0), 255)
    project.masks["player_art"].rectangle((1, 1, project.width - 2, project.height - 2), 255)
    background = image.copy()
    foreground = Image.new("RGBA", image.size, (0, 0, 0, 0)); foreground.paste((30, 50, 70, 255), (0, 0, project.width, 1))
    return BuilderRenderState({}, result, image, result.provenance, background, foreground, project.masks["player_art"].image())


def source_model(tmp_path, project):
    path = tmp_path / "source.png"; Image.new("RGBA", (project.width, project.height), (1, 2, 3, 255)).save(path)
    return SourceCard("s", "Synthetic source", str(path), project.width, project.height, "RGBA", True, "f", "p", reference=True)


def test_export_v2_exact_rgba_and_card_editor_loads_it(tmp_path):
    project = BuilderProject.create("Synthetic Tier", "synthetic_tier", 8, 10); project.sources.append(source_model(tmp_path, project))
    for region in project.text_regions.values(): region.x=1; region.y=1; region.width=2; region.height=2; region.clean=True
    state = export_state(project)
    target = TemplateExportService().export(project, state, tmp_path / "templates", include_diagnostics=True)
    assert {"background.png", "foreground.png", "player_mask.png", "template.json", "preview.png"} <= {item.name for item in target.iterdir()}
    for name in ("background.png", "foreground.png"):
        with Image.open(target / name) as image: assert image.size == (8, 10) and image.mode == "RGBA"
    loaded = TemplateService(tmp_path / "templates").load(target)
    assert loaded.template_version == 2 and loaded.native_size == (8, 10)
    assert loaded.canvas.resolution_status == "working"
    definition = json.loads((target / "template.json").read_text())
    assert definition["text_fields"]["name"]["force_uppercase"] is True
    assert definition["text_fields"]["name"]["fit_mode"] == "scale_to_fit"
    assert "safe_inset_left" in definition["text_fields"]["name"]


def test_diagnostics_not_in_runtime_layer_list(tmp_path):
    project = BuilderProject.create("Synthetic Tier", "synthetic_tier", 8, 10); project.sources.append(source_model(tmp_path, project))
    target = TemplateExportService().export(project, export_state(project), tmp_path, allow_warnings=True)
    definition = json.loads((target / "template.json").read_text())
    assert set(definition["layers"].values()) == {"background.png", "foreground.png", "player_mask.png"}
    assert "diagnostics" not in definition["layers"]


def test_unresolved_and_manual_pixel_warnings_require_override(tmp_path):
    project = BuilderProject.create("Synthetic Tier", "synthetic_tier", 8, 10); project.sources.append(source_model(tmp_path, project))
    project.masks["unresolved"].rectangle((0, 0, 1, 1), 255); project.manual_pixels["2,2"] = [1, 2, 3, 4]
    report = TemplateExportService().validate(project, export_state(project))
    assert any("unresolved" in warning for warning in report.warnings)
    assert any("manually entered" in warning for warning in report.warnings)
    with pytest.raises(TemplateExportError, match="explicit override"):
        TemplateExportService().export(project, export_state(project), tmp_path)


def test_critical_validation_errors_block_export(tmp_path):
    project = BuilderProject.create("Bad", "Bad ID", 8, 10)
    with pytest.raises(TemplateExportError, match="Export blocked"):
        TemplateExportService().export(project, export_state(project), tmp_path, allow_warnings=True)


def test_extraction_report_contains_measured_counts(tmp_path):
    project = BuilderProject.create("Synthetic Tier", "synthetic_tier", 8, 10); project.sources.append(source_model(tmp_path, project))
    target = TemplateExportService().export(project, export_state(project), tmp_path, allow_warnings=True)
    report = json.loads((target / "diagnostics" / "extraction_report.json").read_text())
    assert report["source_count"] == 1
    assert report["template_version"] == 2
    assert "pixel-perfect" in report["measurement_note"]
