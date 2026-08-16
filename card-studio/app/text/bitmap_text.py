"""Deterministic layout and compositing for authentic bitmap glyphs."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from app.text.glyph_atlas import GlyphAtlas, GlyphAtlasError


@dataclass(frozen=True, slots=True)
class TextFieldLayout:
    role: str
    text: str
    bounds: tuple[int, int, int, int]
    safe_bounds: tuple[int, int, int, int]
    scale: float
    tracking: float
    fitted: bool
    missing_glyphs: tuple[str, ...] = ()
    glyph_bounds: tuple[tuple[int, int, int, int], ...] = ()
    warning: str = ""


@dataclass(slots=True)
class BitmapTextRenderer:
    styles_root: Path
    _cache: dict[tuple[str, str], GlyphAtlas] = field(default_factory=dict, init=False)

    def atlas(self, style_id: str, role: str) -> GlyphAtlas:
        key = (style_id, role)
        if key not in self._cache:
            self._cache[key] = GlyphAtlas.load(self.styles_root / style_id, role)
        return self._cache[key]

    def render_field(
        self,
        canvas: Image.Image,
        text: str,
        style_id: str,
        role: str,
        field: dict[str, Any],
        diagnostics: bool = False,
    ) -> TextFieldLayout:
        atlas = self.atlas(style_id, role)
        safe = self._safe_bounds(field)
        missing = atlas.missing(text)
        if not text:
            return TextFieldLayout(role, text, (safe[0], safe[1], 0, 0), safe, 1.0, atlas.default_tracking, True)
        if missing:
            return TextFieldLayout(
                role,
                text,
                (safe[0], safe[1], 0, 0),
                safe,
                1.0,
                atlas.default_tracking,
                False,
                missing,
                warning=f"Missing authentic {role} glyphs: {', '.join(repr(value) for value in missing)}",
            )

        tracking, scale, fits = self._fit(atlas, text, safe[2], field)
        if not fits:
            return TextFieldLayout(
                role,
                text,
                (safe[0], safe[1], 0, 0),
                safe,
                scale,
                tracking,
                False,
                warning=f"{role.title()} text is too wide for its safe region.",
            )

        strip, local_boxes = self._assemble(atlas, text, tracking)
        if scale != 1.0:
            width = max(1, round(strip.width * scale))
            height = max(1, round(strip.height * scale))
            strip = strip.resize((width, height), Image.Resampling.LANCZOS)
            local_boxes = tuple(
                (round(x * scale), round(y * scale), max(1, round(w * scale)), max(1, round(h * scale)))
                for x, y, w, h in local_boxes
            )

        alignment = str(field.get("alignment") or "left")
        if alignment == "center":
            left = safe[0] + (safe[2] - strip.width) // 2
        elif alignment == "right":
            left = safe[0] + safe[2] - strip.width
        else:
            left = safe[0]
        target_baseline = round(float(field.get("baseline", safe[1] + safe[3])))
        source_baseline = round(float(field.get("source_baseline", atlas.baseline)) * scale)
        top = target_baseline - source_baseline
        minimum_top = safe[1]
        maximum_top = safe[1] + safe[3] - strip.height
        top = max(minimum_top, min(top, maximum_top))

        # A region mask is the final safety net. Fitting is checked first so no
        # partial glyph can be silently accepted.
        layer = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
        shadow = field.get("shadow")
        if isinstance(shadow, dict):
            color = shadow.get("color", (0, 0, 0, 160))
            if isinstance(color, (list, tuple)) and len(color) == 4:
                shadow_color = tuple(max(0, min(255, int(value))) for value in color)
                shadow_strip = Image.new("RGBA", strip.size, shadow_color)
                shadow_alpha = strip.getchannel("A").point(
                    lambda value: round(value * shadow_color[3] / 255)
                )
                shadow_strip.putalpha(shadow_alpha)
                layer.alpha_composite(
                    shadow_strip,
                    (
                        left + int(shadow.get("offset_x", 1)),
                        top + int(shadow.get("offset_y", 1)),
                    ),
                )
        layer.alpha_composite(strip, (left, top))
        region_mask = Image.new("L", canvas.size, 0)
        ImageDraw.Draw(region_mask).rectangle(
            (safe[0], safe[1], safe[0] + safe[2] - 1, safe[1] + safe[3] - 1), fill=255
        )
        layer.putalpha(Image.composite(layer.getchannel("A"), Image.new("L", canvas.size, 0), region_mask))
        canvas.alpha_composite(layer)

        glyph_bounds = tuple((left + x, top + y, width, height) for x, y, width, height in local_boxes)
        bounds = (left, top, strip.width, strip.height)
        if diagnostics:
            draw = ImageDraw.Draw(canvas)
            draw.rectangle((safe[0], safe[1], safe[0] + safe[2] - 1, safe[1] + safe[3] - 1), outline=(0, 255, 255, 255))
            draw.line((safe[0], target_baseline, safe[0] + safe[2] - 1, target_baseline), fill=(255, 80, 160, 255))
            draw.rectangle((left, top, left + strip.width - 1, top + strip.height - 1), outline=(255, 220, 0, 255))
            for x, y, width, height in glyph_bounds:
                draw.rectangle((x, y, x + width - 1, y + height - 1), outline=(100, 255, 100, 180))
        return TextFieldLayout(role, text, bounds, safe, scale, tracking, True, glyph_bounds=glyph_bounds)

    @staticmethod
    def _safe_bounds(field: dict[str, Any]) -> tuple[int, int, int, int]:
        x = int(field.get("x", 0))
        y = int(field.get("y", 0))
        width = int(field.get("width", 0))
        height = int(field.get("height", 0))
        left = int(field.get("safe_inset_left", 0))
        right = int(field.get("safe_inset_right", 0))
        top = int(field.get("safe_inset_top", 0))
        bottom = int(field.get("safe_inset_bottom", 0))
        maximum_width = int(field.get("maximum_width", field.get("max_width", width - left - right)))
        return x + left, y + top, max(0, min(width - left - right, maximum_width)), max(0, height - top - bottom)

    @staticmethod
    def _fit(atlas: GlyphAtlas, text: str, safe_width: int, field: dict[str, Any]) -> tuple[float, float, bool]:
        preferred = float(field.get("preferred_tracking", atlas.default_tracking))
        minimum = float(field.get("minimum_tracking", atlas.minimum_tracking))
        tracking = preferred
        while tracking > minimum and atlas.measure(text, tracking) > safe_width:
            tracking = max(minimum, round(tracking - 0.25, 2))
        width = atlas.measure(text, tracking)
        scale = min(1.0, safe_width / width) if width else 1.0
        minimum_scale = float(field.get("min_scale", 1.0))
        if scale < minimum_scale:
            return tracking, minimum_scale, False
        return tracking, scale, True

    @staticmethod
    def _assemble(atlas: GlyphAtlas, text: str, tracking: float) -> tuple[Image.Image, tuple[tuple[int, int, int, int], ...]]:
        measured = max(1, math.ceil(atlas.measure(text, tracking)))
        strip = Image.new("RGBA", (measured + 2, atlas.line_height), (0, 0, 0, 0))
        x = 0.0
        previous = ""
        boxes: list[tuple[int, int, int, int]] = []
        for index, character in enumerate(text):
            glyph = atlas.glyphs[character]
            if index and previous:
                x += tracking + atlas.kerning.get(previous + character, 0.0)
            glyph_image = atlas.crop(character)
            left = round(x + glyph.left_bearing)
            top = round(glyph.vertical_offset + (atlas.baseline - glyph.baseline))
            strip.alpha_composite(glyph_image, (left, top))
            boxes.append((left, top, glyph_image.width, glyph_image.height))
            x += glyph.advance
            previous = character
        used = max((left + width for left, _top, width, _height in boxes), default=1)
        used = max(1, min(strip.width, used))
        strip = strip.crop((0, 0, used, strip.height))

        # Source crops deliberately retain a one-pixel antialiasing guard.
        # Ignore only fully transparent outer guard columns when aligning the
        # finished line, so visual ink—not extraction padding—is centered.
        alpha_bounds = strip.getchannel("A").getbbox()
        if alpha_bounds:
            optical_left, _top, optical_right, _bottom = alpha_bounds
            strip = strip.crop((optical_left, 0, optical_right, strip.height))
            boxes = [
                (left - optical_left, top, width, height)
                for left, top, width, height in boxes
            ]
        return strip, tuple(boxes)


def load_renderer(styles_root: Path) -> BitmapTextRenderer:
    if not styles_root.is_dir():
        raise GlyphAtlasError(f"Text-style resources were not found: {styles_root}")
    return BitmapTextRenderer(styles_root)
