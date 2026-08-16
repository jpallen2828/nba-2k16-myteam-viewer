from __future__ import annotations

import json
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def template_factory(tmp_path):
    def create(
        *,
        width: int = 8,
        height: int = 10,
        missing_layer: str | None = None,
        mismatched_layer: str | None = None,
        canvas_override: dict | None = None,
    ) -> Path:
        directory = tmp_path / "test_tier"
        directory.mkdir(exist_ok=True)
        canvas = canvas_override if canvas_override is not None else {"width": width, "height": height}
        data = {
            "template_version": 1,
            "template_id": "test_tier",
            "display_name": "Test Tier",
            "canvas": canvas,
            "layers": {
                "background": "background.png",
                "player_mask": "player_mask.png",
                "foreground": "foreground.png",
            },
            "player_defaults": {
                "anchor_x": width / 2,
                "anchor_y": height,
                "scale": 1.0,
                "rotation_degrees": 0.0,
                "flip_horizontal": False,
            },
            "text_fields": {"overall": None, "position": None, "name": None},
        }
        (directory / "template.json").write_text(json.dumps(data), encoding="utf-8")
        for name in ("background", "player_mask", "foreground"):
            if name == missing_layer:
                continue
            size = (width + 1, height) if name == mismatched_layer else (width, height)
            if name == "background":
                image = Image.new("RGBA", size, (20, 30, 40, 255))
            elif name == "foreground":
                image = Image.new("RGBA", size, (0, 0, 0, 0))
                if size == (width, height):
                    image.putpixel((width // 2, height // 2), (0, 0, 255, 255))
            else:
                image = Image.new("L", size, 0)
                if size == (width, height):
                    for y in range(2, height - 1):
                        for x in range(2, width - 2):
                            image.putpixel((x, y), 255)
            image.save(directory / f"{name}.png")
        return directory

    return create
