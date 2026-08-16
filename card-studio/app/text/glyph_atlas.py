"""Load immutable RGBA bitmap-glyph atlases and their source metadata."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from PIL import Image


class GlyphAtlasError(RuntimeError):
    """Raised when a packaged atlas is missing or invalid."""


@dataclass(frozen=True, slots=True)
class Glyph:
    character: str
    rect: tuple[int, int, int, int]
    baseline: float
    advance: float
    left_bearing: float
    right_bearing: float
    vertical_offset: float
    source_reference: str
    source_rect: tuple[int, int, int, int] | None
    approved: bool


class GlyphAtlas:
    def __init__(self, image_path: Path, metadata_path: Path) -> None:
        self.image_path = Path(image_path)
        self.metadata_path = Path(metadata_path)
        try:
            with Image.open(self.image_path) as opened:
                self.image = opened.convert("RGBA").copy()
            payload = json.loads(self.metadata_path.read_text(encoding="utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise GlyphAtlasError(f"Could not load glyph atlas '{self.metadata_path}': {exc}") from exc

        self.style_id = str(payload.get("style_id") or "")
        self.role = str(payload.get("role") or "")
        self.line_height = int(payload.get("line_height") or 1)
        self.baseline = float(payload.get("baseline", self.line_height))
        self.default_tracking = float(payload.get("default_tracking") or 0.0)
        self.minimum_tracking = float(payload.get("minimum_tracking") or 0.0)
        self.kerning = {str(pair): float(value) for pair, value in (payload.get("kerning") or {}).items()}
        self.glyphs: dict[str, Glyph] = {}
        for character, item in (payload.get("glyphs") or {}).items():
            rect = tuple(int(value) for value in item.get("rect", ()))
            if len(rect) != 4:
                raise GlyphAtlasError(f"Glyph {character!r} has an invalid atlas rectangle.")
            source_rect = item.get("source_rect")
            self.glyphs[str(character)] = Glyph(
                character=str(character),
                rect=rect,
                baseline=float(item.get("baseline", 0.0)),
                advance=float(item.get("advance", rect[2])),
                left_bearing=float(item.get("left_bearing", 0.0)),
                right_bearing=float(item.get("right_bearing", 0.0)),
                vertical_offset=float(item.get("vertical_offset", 0.0)),
                source_reference=str(item.get("source_reference") or ""),
                source_rect=tuple(int(value) for value in source_rect) if source_rect else None,
                approved=bool(item.get("approved", False)),
            )

    @classmethod
    def load(cls, style_directory: Path, role: str) -> "GlyphAtlas":
        return cls(style_directory / f"{role}_atlas.png", style_directory / f"{role}_atlas.json")

    def missing(self, text: str) -> tuple[str, ...]:
        return tuple(sorted({character for character in text if character not in self.glyphs}))

    def crop(self, character: str) -> Image.Image:
        glyph = self.glyphs[character]
        x, y, width, height = glyph.rect
        return self.image.crop((x, y, x + width, y + height))

    def measure(self, text: str, tracking: float | None = None) -> float:
        if not text:
            return 0.0
        actual_tracking = self.default_tracking if tracking is None else float(tracking)
        cursor = 0.0
        visual_right = 0.0
        previous = ""
        for index, character in enumerate(text):
            glyph = self.glyphs.get(character)
            if glyph is None:
                continue
            if index and previous:
                cursor += actual_tracking + self.kerning.get(previous + character, 0.0)
            visual_right = max(visual_right, cursor + glyph.left_bearing + glyph.rect[2])
            cursor += glyph.advance
            previous = character
        return max(0.0, visual_right)
