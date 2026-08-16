from pathlib import Path

import pytest

from app.services.template_service import TemplateService
from app.utilities.validation import TemplateValidationError


def test_valid_template_loads(template_factory, tmp_path):
    directory = template_factory()
    template = TemplateService(tmp_path).load(directory)
    assert template.template_id == "test_tier"
    assert template.native_size == (8, 10)


def test_missing_template_json_fails_cleanly(tmp_path):
    directory = tmp_path / "empty"
    directory.mkdir()
    with pytest.raises(TemplateValidationError, match="Missing template definition"):
        TemplateService(tmp_path).load(directory)


def test_missing_layer_fails_cleanly(template_factory, tmp_path):
    directory = template_factory(missing_layer="foreground")
    with pytest.raises(TemplateValidationError, match="Missing foreground layer"):
        TemplateService(tmp_path).load(directory)


def test_incorrect_layer_dimensions_fail(template_factory, tmp_path):
    directory = template_factory(mismatched_layer="background")
    with pytest.raises(TemplateValidationError, match="background.png is"):
        TemplateService(tmp_path).load(directory)


@pytest.mark.parametrize("canvas", [{"width": 0, "height": 10}, {"width": 8, "height": -1}, {"width": "8", "height": 10}])
def test_invalid_canvas_size_fails(template_factory, tmp_path, canvas):
    directory = template_factory(canvas_override=canvas)
    with pytest.raises(TemplateValidationError, match="positive integer"):
        TemplateService(tmp_path).load(directory)
