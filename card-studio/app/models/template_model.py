"""Validated, tier-based template data structures."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CanvasSize:
    width: int
    height: int
    resolution_status: str = "working"


@dataclass(frozen=True, slots=True)
class LayerFiles:
    background: Path
    player_mask: Path
    foreground: Path


@dataclass(frozen=True, slots=True)
class PlayerDefaults:
    anchor_x: float
    anchor_y: float
    scale: float = 1.0
    rotation_degrees: float = 0.0
    flip_horizontal: bool = False


@dataclass(frozen=True, slots=True)
class CardTemplate:
    template_version: int
    template_id: str
    display_name: str
    directory: Path
    canvas: CanvasSize
    layers: LayerFiles
    player_defaults: PlayerDefaults
    text_fields: dict[str, Any] = field(default_factory=dict)
    extraction: dict[str, Any] = field(default_factory=dict)

    @property
    def native_size(self) -> tuple[int, int]:
        return self.canvas.width, self.canvas.height
