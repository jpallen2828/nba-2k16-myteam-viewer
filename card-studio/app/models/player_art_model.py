"""Player artwork source and deterministic transform settings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class PlayerTransform:
    """Bottom-center anchored transformation in native card pixels."""

    x: float
    y: float
    scale: float = 1.0
    rotation_degrees: float = 0.0
    flip_horizontal: bool = False

    def to_dict(self) -> dict[str, float | bool]:
        return {
            "x": self.x,
            "y": self.y,
            "scale": self.scale,
            "rotation_degrees": self.rotation_degrees,
            "flip_horizontal": self.flip_horizontal,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PlayerTransform":
        return cls(
            x=float(data.get("x", 0.0)),
            y=float(data.get("y", 0.0)),
            scale=float(data.get("scale", 1.0)),
            rotation_degrees=float(data.get("rotation_degrees", 0.0)),
            flip_horizontal=bool(data.get("flip_horizontal", False)),
        )


@dataclass(slots=True)
class PlayerArt:
    source_path: Path | None
    transform: PlayerTransform
    source_width: int = 0
    source_height: int = 0
    has_transparency: bool = True
