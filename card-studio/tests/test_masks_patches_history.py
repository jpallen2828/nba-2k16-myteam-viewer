import numpy as np
from PIL import Image

from app.builder.analysis.patching import PROVENANCE_MANUAL, apply_edits
from app.builder.models import BuilderProject, MaskModel, PatchOperation
from app.builder.services.history_service import HistoryService


def test_mask_brush_erase_rectangle_polygon_invert_and_fill():
    mask = MaskModel("test", 10, 10)
    mask.apply_brush(5, 5, 3, 255)
    assert mask.array()[5, 5] == 255
    mask.apply_brush(5, 5, 1, 0)
    assert mask.array()[5, 5] == 0
    mask.rectangle((0, 0, 2, 2), 255)
    mask.polygon([(6, 6), (9, 6), (9, 9)], 255)
    assert mask.array()[1, 1] == 255 and mask.array()[7, 8] == 255
    before = mask.array().copy(); mask.invert()
    assert np.array_equal(mask.array(), 255 - before)
    mask.clear(); assert not np.any(mask.array())
    mask.fill(); assert np.all(mask.array() == 255)


def test_hard_edge_and_explicit_feather():
    mask = MaskModel("test", 10, 10)
    mask.rectangle((2, 2, 7, 7), 255)
    assert set(np.unique(mask.array())) <= {0, 255}
    mask.apply_feather(2)
    assert mask.hard_edge is False and mask.feather == 2
    assert len(np.unique(mask.array())) > 2


def test_mask_saved_dimensions_rejected_when_wrong():
    mask = MaskModel("test", 3, 4)
    try:
        mask.set_array(np.zeros((4, 4), np.uint8))
        assert False
    except ValueError as exc:
        assert "3 x 4" in str(exc)


def test_same_coordinate_and_offset_patch_and_provenance():
    candidate = Image.new("RGBA", (4, 4), (0, 0, 0, 255))
    source = Image.new("RGBA", (4, 4), (0, 0, 0, 255)); source.putpixel((2, 1), (9, 8, 7, 6))
    patches = [PatchOperation("s", [(2, 1)]), PatchOperation("s", [(1, 1)], 1, 0)]
    output, provenance = apply_edits(candidate, {"s": source}, {"s": 3}, patches, {})
    assert output.getpixel((2, 1)) == (9, 8, 7, 6)
    assert output.getpixel((1, 1)) == (9, 8, 7, 6)
    assert provenance[1, 1] == 3
    assert source.getpixel((2, 1)) == (9, 8, 7, 6)


def test_manual_pixel_is_tracked_separately():
    output, provenance = apply_edits(Image.new("RGBA", (2, 2)), {}, {}, [], {"1,1": [1, 2, 3, 4]})
    assert output.getpixel((1, 1)) == (1, 2, 3, 4)
    assert provenance[1, 1] == PROVENANCE_MANUAL


def test_history_undo_and_redo_restores_mask_and_pixels():
    project = BuilderProject.create("History", "history", 6, 6)
    history = HistoryService()
    before = project.snapshot(); project.masks["foreground"].rectangle((1, 1, 3, 3), 255); project.manual_pixels["2,2"] = [1, 2, 3, 4]
    history.record("Stroke", before, project)
    undone = history.undo(project)
    assert not np.any(undone.masks["foreground"].array()) and not undone.manual_pixels
    redone = history.redo(undone)
    assert redone.masks["foreground"].array()[2, 2] == 255
    assert redone.manual_pixels["2,2"] == [1, 2, 3, 4]
