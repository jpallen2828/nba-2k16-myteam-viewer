import numpy as np
from PIL import Image
import pytest

from app.builder.analysis.alignment import propose_alignment
from app.builder.analysis.normalization import NormalizationError, normalize_source
from app.builder.models import SourceTransform


def patterned(size=(64, 64)):
    data = np.zeros((size[1], size[0], 4), dtype=np.uint8)
    data[:, :, 3] = 255
    data[8:18, 10:25, :3] = (255, 40, 20)
    data[35:52, 30:46, :3] = (20, 210, 100)
    return Image.fromarray(data, "RGBA")


def test_identity_normalization_is_exact_and_source_immutable():
    source = patterned((32, 40)); before = source.tobytes()
    result = normalize_source(source, source.size, SourceTransform())
    assert result.tobytes() == before
    assert source.tobytes() == before
    assert result is not source


def test_rectangular_crop_maps_to_output_dimensions():
    source = patterned((64, 64))
    result = normalize_source(source, (32, 32), SourceTransform(crop_rect=(8, 8, 56, 56)))
    assert result.size == (32, 32)


def test_four_corner_perspective_mapping():
    source = patterned((64, 64))
    transform = SourceTransform(corners=[(5, 4), (58, 7), (55, 59), (7, 57)])
    result = normalize_source(source, (40, 50), transform)
    assert result.size == (40, 50)
    assert result.mode == "RGBA"


@pytest.mark.parametrize("corners", [[(0, 0)] * 4, [(0, 0), (4, 4), (0, 4), (4, 0)], [(0, 0)] * 3])
def test_invalid_corner_configurations_raise(corners):
    with pytest.raises(NormalizationError):
        normalize_source(patterned(), (32, 32), SourceTransform(corners=corners))


def test_known_integer_translation_is_recovered():
    reference = patterned()
    moving = normalize_source(reference, reference.size, SourceTransform(translate_x=5, translate_y=-3))
    proposal = propose_alignment(reference, moving, integer_only=True, allow_rotation_scale=False)
    assert proposal.translate_x == -5
    assert proposal.translate_y == 3
    assert isinstance(proposal.translate_x, float)


def test_alignment_mask_is_dimension_checked():
    with pytest.raises(ValueError, match="mask dimensions"):
        propose_alignment(patterned(), patterned(), np.ones((4, 4), np.uint8))


def test_known_small_rotation_is_estimated_with_correction_sign():
    reference = patterned()
    moving = normalize_source(reference, reference.size, SourceTransform(rotation_degrees=3, subpixel=True))
    proposal = propose_alignment(reference, moving, integer_only=False, allow_rotation_scale=True)
    assert proposal.rotation_degrees == pytest.approx(-3, abs=.35)
    assert proposal.confidence > .8


def test_alignment_mask_honored_for_masked_feature():
    reference = patterned()
    moving = normalize_source(reference, reference.size, SourceTransform(translate_x=3, translate_y=2))
    mask = np.zeros((64, 64), np.uint8); mask[4:28, 4:32] = 255
    proposal = propose_alignment(reference, moving, mask, integer_only=True, allow_rotation_scale=False)
    assert (proposal.translate_x, proposal.translate_y) == (-3, -2)


def test_low_information_alignment_warns():
    blank = Image.new("RGBA", (32, 32), (0, 0, 0, 255))
    proposal = propose_alignment(blank, blank, integer_only=True, allow_rotation_scale=False)
    assert proposal.warning is not None
