import numpy as np
from PIL import Image
import pytest

from app.builder.analysis.composite import generate_composite


def solid(value, alpha=255):
    return Image.new("RGBA", (3, 2), (value, value * 2, value * 3, alpha))


def test_median_and_trimmed_mean_output():
    images = [solid(0), solid(10), solid(20), solid(100), solid(255)]
    assert generate_composite(images, "median").image.getpixel((0, 0)) == (20, 40, 60, 255)
    assert generate_composite(images, "trimmed_mean", trim_fraction=.2).image.getpixel((0, 0)) == (43, 87, 115, 255)


def test_exact_rgba_mode_tie_is_deterministic_first_source():
    images = [solid(4), solid(9), solid(9), solid(4)]
    first = generate_composite(images, "exact_rgba_mode")
    second = generate_composite(images, "exact_rgba_mode")
    assert first.image.tobytes() == second.image.tobytes()
    assert first.image.getpixel((1, 1)) == solid(4).getpixel((0, 0))


def test_rgb_mode_analyzes_alpha_separately():
    images = [solid(10, 10), solid(10, 200), solid(30, 255)]
    result = generate_composite(images, "rgb_mode_alpha")
    assert result.image.getpixel((0, 0)) == (10, 20, 30, 200)


def test_consensus_and_variance_are_measurable():
    result = generate_composite([solid(10), solid(10), solid(20)], "exact_rgba_mode")
    assert result.agreement_count[0, 0] == 2
    assert result.consensus[0, 0] == pytest.approx(2 / 3)
    assert result.variance[0, 0] > 0
    assert result.alpha_variance[0, 0] == 0


def test_region_override_changes_only_masked_pixels():
    images = [solid(0), solid(10), solid(20)]
    mask = np.zeros((2, 3), np.uint8); mask[0, 0] = 255
    result = generate_composite(images, "source_priority", region_overrides=[(mask, "median")])
    assert result.image.getpixel((0, 0)) == solid(10).getpixel((0, 0))
    assert result.image.getpixel((1, 0)) == solid(0).getpixel((0, 0))


def test_maximum_difference_and_alpha_variance():
    result = generate_composite([solid(10, 0), solid(10, 255)], "median")
    assert result.maximum_difference[0, 0] == 255
    assert result.alpha_variance[0, 0] > 0


def test_mismatched_or_empty_sources_are_rejected():
    with pytest.raises(ValueError): generate_composite([])
    with pytest.raises(ValueError): generate_composite([solid(1), Image.new("RGBA", (1, 1))])
